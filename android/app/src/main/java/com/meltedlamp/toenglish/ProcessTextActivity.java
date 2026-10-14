package com.meltedlamp.toenglish;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.os.Bundle;
import android.text.TextUtils;
import android.text.method.ScrollingMovementMethod;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ProcessTextActivity extends Activity {
    private static final String[] OFTEN = {
            "es", "fr", "de", "it", "pt", "ru", "bg", "ja", "ko", "zh-CN", "zh-TW",
            "ar", "hi", "tr", "nl", "pl", "uk", "vi", "th", "id", "el", "he", "sv"
    };

    private final ExecutorService pool = Executors.newSingleThreadExecutor();

    private static final int MAX_CHARS = 12000;
    static final String PREFS = "translator";
    static final String KEY_SOURCE = "source";
    static final String KEY_TARGET = "target";

    private FrameLayout stage;
    private TextView title;
    private TextView preview;
    private TextView status;
    private LinearLayout expandRow;
    private Button lessButton;
    private Button moreButton;
    private TextView amountView;
    private String selected = "";
    private String passage = "";
    private int rangeStart;
    private int rangeEnd;
    private int anchorStart;
    private int anchorEnd;
    private boolean sideMode;
    private boolean grewForward = true;
    private String lastSource = "auto";
    private String lastTarget = "en";
    private final ArrayDeque<int[]> rangeHistory = new ArrayDeque<>();
    private boolean readOnly = true;
    private String step = "from";
    private String pendingSource = "auto";
    private int generation;
    private int padLeft;
    private int padTop;
    private int padRight;
    private int padBottom;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setResult(RESULT_CANCELED);
        Brain.open(getFilesDir());
        Translator.loadNames(getAssets());
        setContentView(R.layout.process_text);
        stage = findViewById(R.id.stage);
        title = findViewById(R.id.title);
        preview = findViewById(R.id.preview);
        status = findViewById(R.id.status);
        expandRow = findViewById(R.id.expand);
        lessButton = findViewById(R.id.less);
        moreButton = findViewById(R.id.more);
        amountView = findViewById(R.id.amount);
        lessButton.setBackgroundTintList(null);
        moreButton.setBackgroundTintList(null);
        lessButton.setOnClickListener(view -> expandLess());
        moreButton.setOnClickListener(view -> expandMore());
        preview.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        View root = findViewById(R.id.root);
        padLeft = root.getPaddingLeft();
        padTop = root.getPaddingTop();
        padRight = root.getPaddingRight();
        padBottom = root.getPaddingBottom();
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(padLeft, padTop, padRight, padBottom + insets.getSystemWindowInsetBottom());
            return insets;
        });
        root.requestApplyInsets();
        if (!readIntent(getIntent())) {
            finish();
            return;
        }
        loadLanguages();
        beginTranslate(lastSource, lastTarget);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        generation++;
        if (!readIntent(intent)) {
            finish();
            return;
        }
        loadLanguages();
        beginTranslate(lastSource, lastTarget);
    }

    @Override
    protected void onDestroy() {
        generation++;
        pool.shutdownNow();
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if ("into".equals(step)) {
            showFrom();
            return;
        }
        if ("from".equals(step)) {
            beginTranslate(lastSource, lastTarget);
            return;
        }
        setResult(RESULT_CANCELED);
        super.onBackPressed();
    }

    private boolean readIntent(Intent intent) {
        rangeHistory.clear();
        sideMode = false;
        grewForward = true;
        if (intent == null) return false;
        if (SideTranslateService.ACTION_SIDE.equals(intent.getAction())) {
            String raw = intent.getStringExtra(SideTranslateService.EXTRA_PASSAGE);
            int start = intent.getIntExtra(SideTranslateService.EXTRA_START, 0);
            int end = intent.getIntExtra(SideTranslateService.EXTRA_END, raw == null ? 0 : raw.length());
            if (!bindRange(raw, start, end)) return false;
            readOnly = true;
            sideMode = true;
            selected = currentSlice();
            return !selected.isEmpty();
        }
        if (!Intent.ACTION_PROCESS_TEXT.equals(intent.getAction())) return false;
        CharSequence raw = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
        selected = raw == null ? "" : raw.toString().trim();
        readOnly = intent.getBooleanExtra(Intent.EXTRA_PROCESS_TEXT_READONLY, true);
        if (selected.isEmpty()) return false;
        passage = selected;
        rangeStart = 0;
        rangeEnd = selected.length();
        anchorStart = 0;
        anchorEnd = selected.length();
        adoptLargerPassage(selected);
        return true;
    }

    private boolean bindRange(String raw, int start, int end) {
        passage = raw == null ? "" : raw;
        if (passage.isEmpty()) return false;
        if (start > end) {
            int swap = start;
            start = end;
            end = swap;
        }
        rangeStart = Math.max(0, Math.min(start, passage.length()));
        rangeEnd = Math.max(rangeStart, Math.min(end, passage.length()));
        if (rangeStart == rangeEnd) return false;
        anchorStart = rangeStart;
        anchorEnd = rangeEnd;
        return true;
    }

    private void adoptLargerPassage(String wanted) {
        SideTranslateService.Snapshot snap = SideTranslateService.latest();
        if (snap == null || wanted.isEmpty()) return;
        String window = snap.text;
        if (window == null || snap.start < 0 || snap.end > window.length() || snap.start >= snap.end) return;
        String slice = window.substring(snap.start, snap.end).trim();
        if (slice.isEmpty() || !slice.equals(wanted)) return;
        passage = window;
        rangeStart = snap.start;
        rangeEnd = snap.end;
        anchorStart = rangeStart;
        anchorEnd = rangeEnd;
        sideMode = passage.length() > (anchorEnd - anchorStart);
        selected = currentSlice();
    }

    private void showFrom() {
        showLanguageStep("from", "Which language is this?", true, code -> {
            pendingSource = code;
            showInto();
        });
    }

    private void showInto() {
        showLanguageStep("into", "Translate it into…", false, code -> beginTranslate(pendingSource, code));
    }

    private void showLanguageStep(String nextStep, String heading, boolean includeDetect, java.util.function.Consumer<String> onPick) {
        step = nextStep;
        title.setOnClickListener(null);
        title.setClickable(false);
        title.setText(heading);
        selected = currentSlice();
        showPassage();
        status.setText(sideMode
                ? "More adds the next sentence. Less goes back toward what you first held."
                : "This is the text you selected.");
        syncExpand();
        List<LangRow> rows = languageRows(includeDetect);
        ListView list = new ListView(this);
        list.setAdapter(new LanguageAdapter(rows));
        list.setDivider(new ColorDrawable(0xFF3A342C));
        list.setDividerHeight(dp(1));
        list.setBackgroundColor(0xFF1C1A17);
        list.setOnItemClickListener((parent, view, position, id) -> {
            LangRow row = rows.get(position);
            if (row.code == null) return;
            onPick.accept(row.code);
        });
        setStageHeight(dp(sideMode ? 240 : 340));
        stage.removeAllViews();
        stage.addView(list, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        placeWindow();
    }

    private void beginTranslate(String source, String target) {
        step = "result";
        lastSource = source;
        lastTarget = target;
        saveLanguages();
        selected = currentSlice();
        showPassage();
        syncExpand();
        final int gen = ++generation;
        final String text = selected;
        title.setOnClickListener(null);
        title.setClickable(false);
        title.setText("Translating…");
        status.setText("");
        setStageHeight(ViewGroup.LayoutParams.WRAP_CONTENT);
        stage.removeAllViews();
        pool.execute(() -> {
            String payload;
            try {
                payload = Translator.translate(text, source, target);
            } catch (Exception ex) {
                payload = "{\"error\":\"Could not reach the translator. Check your connection and try again.\"}";
            }
            String result = payload;
            runOnUiThread(() -> {
                if (gen != generation || isFinishing()) return;
                showResult(result);
            });
        });
    }

    private void showResult(String payload) {
        JSONObject data;
        try {
            data = new JSONObject(payload);
        } catch (Exception ex) {
            showFrom();
            status.setText("Translation failed.");
            return;
        }
        String translation = data.optString("translation", data.optString("english", "")).trim();
        if (translation.isEmpty()) {
            showFrom();
            status.setText(data.optString("error", "Translation failed."));
            return;
        }
        step = "result";
        String language = data.optString("language", "Unknown");
        String target = data.optString("target", "English");
        title.setText(language.equals(target) ? language : language + " → " + target);
        showPassage();
        syncExpand();
        String note = data.optString("note", "");
        status.setText(note.isEmpty() ? "Tap the languages above to change them." : note);
        TextView body = new TextView(this);
        body.setText(translation);
        body.setTextColor(0xFFF4EFE6);
        body.setTextSize(22);
        body.setTypeface(Typeface.SERIF);
        body.setLineSpacing(dp(4), 1f);
        body.setTextIsSelectable(true);
        body.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        LinearLayout column = column();
        column.addView(body);
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.END);
        LinearLayout.LayoutParams actionRow = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        actionRow.topMargin = dp(16);
        actions.setLayoutParams(actionRow);
        title.setOnClickListener(view -> showFrom());
        actions.addView(actionButton("Copy", false, () -> copyTranslation(translation)));
        if (!readOnly) {
            actions.addView(actionButton("Replace", true, () -> replaceSelection(translation)));
        } else {
            actions.addView(actionButton("Done", true, () -> {
                setResult(RESULT_CANCELED);
                finish();
            }));
        }
        column.addView(actions);
        setStageHeight(ViewGroup.LayoutParams.WRAP_CONTENT);
        stage.removeAllViews();
        stage.addView(column);
        placeWindow();
    }

    private void copyTranslation(String translation) {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard == null) {
            status.setText("Couldn't copy that.");
            return;
        }
        clipboard.setPrimaryClip(ClipData.newPlainText("translation", translation));
        status.setText("Copied.");
    }

    private void replaceSelection(String translation) {
        Intent result = new Intent();
        result.putExtra(Intent.EXTRA_PROCESS_TEXT, translation);
        setResult(RESULT_OK, result);
        finish();
    }

    private Button actionButton(String label, boolean solid, Runnable action) {
        Button button = pill(label, solid);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        params.leftMargin = dp(8);
        button.setLayoutParams(params);
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private Button pill(String label, boolean solid) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTransformationMethod(null);
        button.setTextSize(15);
        button.setMinHeight(dp(48));
        button.setMinimumHeight(dp(48));
        button.setPadding(dp(18), dp(10), dp(18), dp(10));
        button.setBackgroundResource(solid ? R.drawable.pill_solid : R.drawable.pill_ghost);
        button.setTextColor(solid ? 0xFF141210 : 0xFFF4EFE6);
        return button;
    }

    private LinearLayout column() {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setLayoutParams(new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        return column;
    }

    private void setStageHeight(int height) {
        ViewGroup.LayoutParams params = stage.getLayoutParams();
        params.height = height;
        stage.setLayoutParams(params);
    }

    private void placeWindow() {
        Window window = getWindow();
        window.setGravity(Gravity.BOTTOM);
        WindowManager.LayoutParams params = window.getAttributes();
        params.width = ViewGroup.LayoutParams.MATCH_PARENT;
        params.height = ViewGroup.LayoutParams.WRAP_CONTENT;
        window.setAttributes(params);
    }

    private List<LangRow> languageRows(boolean includeDetect) {
        List<LangRow> rows = new ArrayList<>();
        Set<String> used = new HashSet<>();
        if (includeDetect) rows.add(new LangRow("auto", "Detect language"));
        rows.add(new LangRow(null, "Often"));
        if (Translator.knownLanguage("en")) {
            rows.add(new LangRow("en", Translator.languageName("en")));
            used.add("en");
        }
        for (String code : OFTEN) {
            if (!Translator.knownLanguage(code) || "en".equals(code)) continue;
            rows.add(new LangRow(code, Translator.languageName(code)));
            used.add(code);
        }
        List<LangRow> more = new ArrayList<>();
        for (String code : Translator.languageCodes()) {
            if (used.contains(code) || "iw".equals(code) || "en".equals(code)) continue;
            more.add(new LangRow(code, Translator.languageName(code)));
        }
        Collections.sort(more, (left, right) -> left.label.compareToIgnoreCase(right.label));
        if (!more.isEmpty()) rows.add(new LangRow(null, "More"));
        rows.addAll(more);
        return rows;
    }

    private void expandMore() {
        if (!canGrow()) return;
        int nextStart = rangeStart;
        int nextEnd = rangeEnd;
        boolean forward = false;
        if (rangeEnd < passage.length()) {
            int forwardEnd = stepForward(passage, rangeEnd);
            if (forwardEnd != rangeEnd) {
                nextEnd = forwardEnd;
                forward = true;
            }
        }
        if (nextEnd == rangeEnd && rangeStart > 0) {
            int backwardStart = stepBackward(passage, rangeStart);
            if (backwardStart != rangeStart) nextStart = backwardStart;
        }
        if (nextStart == rangeStart && nextEnd == rangeEnd) return;
        String next = passage.substring(nextStart, nextEnd).trim();
        if (next.length() > MAX_CHARS) {
            status.setText("Keep it under 12,000 characters.");
            return;
        }
        rangeHistory.addLast(new int[]{rangeStart, rangeEnd});
        rangeStart = nextStart;
        rangeEnd = nextEnd;
        grewForward = forward;
        onRangeChanged();
    }

    private void expandLess() {
        if (rangeHistory.isEmpty()) {
            rangeStart = anchorStart;
            rangeEnd = anchorEnd;
        } else {
            int[] previous = rangeHistory.removeLast();
            rangeStart = previous[0];
            rangeEnd = previous[1];
        }
        grewForward = false;
        onRangeChanged();
    }

    private void onRangeChanged() {
        selected = currentSlice();
        showPassage();
        syncExpand();
        if ("result".equals(step)) beginTranslate(lastSource, lastTarget);
    }

    private void syncExpand() {
        if (expandRow == null) return;
        expandRow.setVisibility(sideMode ? View.VISIBLE : View.GONE);
        if (!sideMode) return;
        String slice = selected == null ? "" : selected;
        int words = wordCount(slice);
        if (words <= 1 && slice.length() > 12 && !slice.contains(" ")) {
            amountView.setText(slice.length() + " characters");
        } else {
            amountView.setText(words + (words == 1 ? " word" : " words"));
        }
        boolean shrunk = rangeStart != anchorStart || rangeEnd != anchorEnd;
        lessButton.setEnabled(!rangeHistory.isEmpty() || shrunk);
        moreButton.setEnabled(canGrow());
    }

    private boolean canGrow() {
        if (passage.isEmpty() || selected.length() >= MAX_CHARS) return false;
        if (rangeEnd < passage.length() && stepForward(passage, rangeEnd) != rangeEnd) return true;
        return rangeStart > 0 && stepBackward(passage, rangeStart) != rangeStart;
    }

    private String currentSlice() {
        if (passage == null || passage.isEmpty()) return selected == null ? "" : selected;
        int start = Math.max(0, Math.min(rangeStart, passage.length()));
        int end = Math.max(start, Math.min(rangeEnd, passage.length()));
        String slice = passage.substring(start, end).trim();
        return slice.isEmpty() ? (selected == null ? "" : selected) : slice;
    }

    private void showPassage() {
        if (sideMode) {
            preview.setMaxLines(4);
            preview.setEllipsize(null);
            preview.setMovementMethod(new ScrollingMovementMethod());
            preview.setText(selected);
            preview.post(() -> {
                if (preview.getLayout() == null) return;
                if (!grewForward) {
                    preview.scrollTo(0, 0);
                    return;
                }
                int extra = preview.getLayout().getLineTop(preview.getLineCount()) - preview.getHeight();
                preview.scrollTo(0, Math.max(0, extra));
            });
            return;
        }
        preview.setMaxLines(3);
        preview.setEllipsize(TextUtils.TruncateAt.END);
        preview.setMovementMethod(null);
        preview.setText(previewOf(selected));
    }

    private static int wordCount(String text) {
        int words = 0;
        boolean inWord = false;
        for (int i = 0; i < text.length(); ) {
            int point = text.codePointAt(i);
            if (Character.isWhitespace(point)) inWord = false;
            else if (!inWord) {
                words++;
                inWord = true;
            }
            i += Character.charCount(point);
        }
        return words;
    }

    private static boolean isStop(char c) {
        return c == '.' || c == '!' || c == '?' || c == '\n'
                || c == '。' || c == '！' || c == '？';
    }

    private static int stepForward(String text, int index) {
        int len = text.length();
        int i = index;
        while (i < len && Character.isWhitespace(text.charAt(i))) i++;
        if (i >= len) return index;
        int words = 0;
        int guard = Math.min(len, i + 90);
        while (i < guard) {
            char c = text.charAt(i);
            i++;
            if (isStop(c)) return i;
            if (Character.isWhitespace(c)) {
                words++;
                while (i < len && Character.isWhitespace(text.charAt(i))) i++;
                if (words >= 8) return Math.min(i, len);
            }
        }
        return i > index ? i : Math.min(len, index + 1);
    }

    private static int stepBackward(String text, int index) {
        int i = index;
        while (i > 0 && Character.isWhitespace(text.charAt(i - 1))) i--;
        if (i <= 0) return 0;
        if (i < index && isStop(text.charAt(i - 1))) {
            i--;
            while (i > 0 && Character.isWhitespace(text.charAt(i - 1))) i--;
        }
        if (i <= 0) return 0;
        int guard = Math.max(0, i - 90);
        int words = 0;
        while (i > guard) {
            char c = text.charAt(i - 1);
            if (isStop(c)) return i;
            i--;
            if (Character.isWhitespace(c)) {
                words++;
                if (words >= 8) {
                    while (i > 0 && Character.isWhitespace(text.charAt(i - 1))) i--;
                    return i;
                }
            }
        }
        return i < index ? i : Math.max(0, index - 1);
    }

    private String previewOf(String text) {
        String oneLine = text.replace('\n', ' ').replaceAll(" +", " ").trim();
        if (oneLine.length() > 160) return oneLine.substring(0, 157) + "…";
        return oneLine;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    static String savedSource(Context context) {
        String value = prefs(context).getString(KEY_SOURCE, "auto");
        if ("auto".equals(value) || Translator.knownLanguage(value)) return value;
        return "auto";
    }

    static String savedTarget(Context context) {
        String value = prefs(context).getString(KEY_TARGET, "en");
        return Translator.knownLanguage(value) ? value : "en";
    }

    static boolean languagesChosen(Context context) {
        SharedPreferences prefs = prefs(context);
        return prefs.contains(KEY_SOURCE) || prefs.contains(KEY_TARGET);
    }

    static void storeLanguages(Context context, String source, String target) {
        if (source == null || source.isEmpty() || (!"auto".equals(source) && !Translator.knownLanguage(source))) {
            source = "auto";
        }
        if (target == null || target.isEmpty() || !Translator.knownLanguage(target)) {
            target = "en";
        }
        prefs(context).edit().putString(KEY_SOURCE, source).putString(KEY_TARGET, target).apply();
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private void loadLanguages() {
        lastSource = savedSource(this);
        lastTarget = savedTarget(this);
    }

    private void saveLanguages() {
        storeLanguages(this, lastSource, lastTarget);
    }

    private static final class LangRow {
        final String code;
        final String label;

        LangRow(String code, String label) {
            this.code = code;
            this.label = label;
        }
    }

    private final class LanguageAdapter extends BaseAdapter {
        private final List<LangRow> rows;

        LanguageAdapter(List<LangRow> rows) {
            this.rows = rows;
        }

        @Override
        public int getCount() {
            return rows.size();
        }

        @Override
        public Object getItem(int position) {
            return rows.get(position);
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public boolean areAllItemsEnabled() {
            return false;
        }

        @Override
        public boolean isEnabled(int position) {
            return rows.get(position).code != null;
        }

        @Override
        public View getView(int position, View convert, ViewGroup parent) {
            TextView view = convert instanceof TextView
                    ? (TextView) convert
                    : new TextView(ProcessTextActivity.this);
            LangRow row = rows.get(position);
            boolean header = row.code == null;
            view.setText(row.label);
            view.setTextColor(header ? 0xFFE38B74 : 0xFFF4EFE6);
            view.setTextSize(header ? 12 : 16);
            view.setAllCaps(header);
            view.setTypeface(Typeface.create("sans-serif", header ? Typeface.BOLD : Typeface.NORMAL));
            view.setPadding(dp(4), dp(header ? 14 : 12), dp(4), dp(12));
            return view;
        }
    }
}
