package com.meltedlamp.toenglish;

import android.accessibilityservice.AccessibilityService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * A small tab on the edge of the screen. It reads text only after a long-press
 * selection, plus the same passage so the sheet can include a bit more of it.
 */
public class SideTranslateService extends AccessibilityService {
    static final String ACTION_SIDE = "com.meltedlamp.toenglish.action.SIDE_TEXT";
    static final String EXTRA_PASSAGE = "passage";
    static final String EXTRA_START = "start";
    static final String EXTRA_END = "end";

    private static final int WINDOW = 12000;

    private static SideTranslateService instance;
    private static volatile Snapshot latest;

    private final Handler main = new Handler(Looper.getMainLooper());
    private SideChip chip;

    static boolean enabled(Context context) {
        String setting = Settings.Secure.getString(
                context.getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (setting == null || setting.isEmpty()) return false;
        String flat = new ComponentName(context, SideTranslateService.class).flattenToString();
        for (String piece : setting.split(":")) {
            if (flat.equalsIgnoreCase(piece)) return true;
        }
        return false;
    }

    static Snapshot latest() {
        return latest;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        chip = new SideChip();
        chip.attach();
    }

    @Override
    public void onDestroy() {
        if (chip != null) chip.detach();
        chip = null;
        if (instance == this) instance = null;
        latest = null;
        super.onDestroy();
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        CharSequence pkg = event.getPackageName();
        if (pkg != null && getPackageName().contentEquals(pkg)) return;
        int type = event.getEventType();
        if (type != AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED
                && type != AccessibilityEvent.TYPE_VIEW_LONG_CLICKED) {
            return;
        }
        AccessibilityNodeInfo source = event.getSource();
        try {
            Snapshot snap = fromNode(source);
            if (snap == null && type == AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED) {
                snap = fromEvent(event);
            }
            if (snap == null) return;
            latest = snap;
            if (chip != null) chip.showReady(true);
        } finally {
            if (source != null) source.recycle();
        }
    }

    private void openSheet() {
        Snapshot fresh = scanActiveSelection();
        Snapshot remembered = latest;
        boolean freshEnough = remembered != null
                && SystemClock.elapsedRealtime() - remembered.at < 30000;
        Snapshot use = fresh != null ? fresh : (freshEnough ? remembered : null);
        if (use == null) {
            Toast.makeText(this, "Long-press the words you want, then tap here.", Toast.LENGTH_SHORT).show();
            return;
        }
        latest = use;
        if (chip != null) chip.showReady(true);
        Intent intent = new Intent(this, ProcessTextActivity.class);
        intent.setAction(ACTION_SIDE);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra(EXTRA_PASSAGE, use.text);
        intent.putExtra(EXTRA_START, use.start);
        intent.putExtra(EXTRA_END, use.end);
        try {
            startActivity(intent);
        } catch (Exception ex) {
            Toast.makeText(this, "Couldn't open the translator.", Toast.LENGTH_SHORT).show();
        }
    }

    private Snapshot scanActiveSelection() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return null;
        try {
            CharSequence pkg = root.getPackageName();
            if (pkg != null && getPackageName().contentEquals(pkg)) return null;
            int[] budget = new int[]{250};
            return walk(root, budget);
        } finally {
            root.recycle();
        }
    }

    private Snapshot walk(AccessibilityNodeInfo node, int[] budget) {
        if (node == null || budget[0]-- <= 0) return null;
        Snapshot own = fromNode(node);
        if (own != null) return own;
        for (int i = 0; i < node.getChildCount() && budget[0] > 0; i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            try {
                Snapshot found = walk(child, budget);
                if (found != null) return found;
            } finally {
                child.recycle();
            }
        }
        return null;
    }

    private static Snapshot fromNode(AccessibilityNodeInfo node) {
        if (node == null || node.isPassword()) return null;
        CharSequence raw = node.getText();
        if (raw == null || raw.length() == 0) return null;
        int start = node.getTextSelectionStart();
        int end = node.getTextSelectionEnd();
        return Snapshot.capture(raw.toString(), start, end);
    }

    private static Snapshot fromEvent(AccessibilityEvent event) {
        if (event.getText() == null || event.getText().isEmpty()) return null;
        CharSequence raw = event.getText().get(0);
        if (raw == null) return null;
        return Snapshot.capture(raw.toString(), event.getFromIndex(), event.getToIndex());
    }

    static final class Snapshot {
        final String text;
        final int start;
        final int end;
        final long at;

        private Snapshot(String text, int start, int end) {
            this.text = text;
            this.start = start;
            this.end = end;
            this.at = SystemClock.elapsedRealtime();
        }

        static Snapshot capture(String raw, int start, int end) {
            if (raw == null || raw.isEmpty()) return null;
            if (start > end) {
                int swap = start;
                start = end;
                end = swap;
            }
            start = Math.max(0, Math.min(start, raw.length()));
            end = Math.max(start, Math.min(end, raw.length()));
            if (start == end) return null;
            if (raw.length() <= WINDOW) return new Snapshot(raw, start, end);
            int span = end - start;
            if (span >= WINDOW) {
                return new Snapshot(raw.substring(start, start + WINDOW), 0, WINDOW);
            }
            int budget = WINDOW - span;
            int before = Math.min(start, budget / 2);
            int after = Math.min(raw.length() - end, budget - before);
            before = Math.min(start, budget - after);
            int from = start - before;
            return new Snapshot(raw.substring(from, end + after), before, before + span);
        }
    }

    private final class SideChip {
        private final WindowManager windows;
        private final WindowManager.LayoutParams params;
        private final FrameLayout holder;
        private final GradientDrawable plate;
        private final SharedPreferences prefs;
        private boolean added;

        SideChip() {
            windows = (WindowManager) getSystemService(WINDOW_SERVICE);
            prefs = getSharedPreferences("side_translate", MODE_PRIVATE);
            plate = new GradientDrawable();
            float radius = dp(16);
            plate.setCornerRadii(new float[]{radius, radius, 0, 0, 0, 0, radius, radius});
            plate.setColor(0xF01C1A17);

            holder = new FrameLayout(SideTranslateService.this);
            holder.setBackground(plate);
            holder.setElevation(dp(8));
            holder.setContentDescription("Translate selected text");
            TextView label = new TextView(SideTranslateService.this);
            FrameLayout.LayoutParams labelParams = new FrameLayout.LayoutParams(dp(128), dp(44));
            labelParams.gravity = Gravity.CENTER;
            label.setLayoutParams(labelParams);
            label.setGravity(Gravity.CENTER);
            label.setRotation(-90f);
            label.setText("Translate");
            label.setTextColor(0xFFF4EFE6);
            label.setTextSize(13);
            label.setTypeface(Typeface.DEFAULT_BOLD);
            holder.addView(label);
            holder.setOnTouchListener(new Drag());
            showReady(false);

            params = new WindowManager.LayoutParams(
                    dp(44),
                    dp(128),
                    WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT);
            params.gravity = Gravity.END | Gravity.CENTER_VERTICAL;
            params.y = prefs.getInt("chip_y", 0);
        }

        void attach() {
            if (added || windows == null) return;
            try {
                windows.addView(holder, params);
                added = true;
            } catch (Exception ex) {
                Toast.makeText(SideTranslateService.this, "Couldn't show the side tab.", Toast.LENGTH_SHORT).show();
            }
        }

        void detach() {
            if (!added || windows == null) return;
            try {
                windows.removeView(holder);
            } catch (Exception ignored) {
            }
            added = false;
        }

        void showReady(boolean ready) {
            main.post(() -> {
                if (holder == null) return;
                plate.setStroke(dp(ready ? 2 : 1), ready ? 0xFFE38B74 : 0xFF3A342C);
                holder.setAlpha(ready ? 1f : 0.72f);
                holder.invalidate();
            });
        }

        private int dp(int value) {
            return Math.round(value * getResources().getDisplayMetrics().density);
        }

        private final class Drag implements View.OnTouchListener {
            private float downY;
            private int startY;
            private boolean dragged;

            @Override
            public boolean onTouch(View view, MotionEvent event) {
                switch (event.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        downY = event.getRawY();
                        startY = params.y;
                        dragged = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        float dy = event.getRawY() - downY;
                        if (Math.abs(dy) > ViewConfiguration.get(view.getContext()).getScaledTouchSlop()) {
                            dragged = true;
                        }
                        if (!dragged) return true;
                        params.y = clamp(startY + Math.round(dy));
                        if (added) windows.updateViewLayout(holder, params);
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (dragged) prefs.edit().putInt("chip_y", params.y).apply();
                        else openSheet();
                        return true;
                    case MotionEvent.ACTION_CANCEL:
                        return true;
                    default:
                        return false;
                }
            }

            private int clamp(int y) {
                int limit = getResources().getDisplayMetrics().heightPixels / 2 - dp(80);
                if (limit < 0) limit = 0;
                return Math.max(-limit, Math.min(limit, y));
            }
        }
    }
}
