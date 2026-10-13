package com.meltedlamp.toenglish;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.os.Bundle;
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

    private FrameLayout stage;
    private TextView title;
    private TextView preview;
    private TextView status;
    private String selected = "";
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
        Translator.loadNames(getAssets());
        setContentView(R.layout.process_text);
        stage = findViewById(R.id.stage);
        title = findViewById(R.id.title);
        preview = findViewById(R.id.preview);
        status = findViewById(R.id.status);
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
        showFrom();
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
        showFrom();
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
        if ("result".equals(step)) {
            showInto();
            return;
        }
        if ("into".equals(step)) {
            showFrom();
            return;
        }
        setResult(RESULT_CANCELED);
        super.onBackPressed();
    }

    private boolean readIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_PROCESS_TEXT.equals(intent.getAction())) return false;
        CharSequence raw = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
        selected = raw == null ? "" : raw.toString().trim();
        readOnly = intent.getBooleanExtra(Intent.EXTRA_PROCESS_TEXT_READONLY, true);
        return !selected.isEmpty();
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
        title.setText(heading);
        preview.setText(previewOf(selected));
        status.setText("This is the text you selected.");
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
        setStageHeight(dp(340));
        stage.removeAllViews();
        stage.addView(list, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        placeWindow();
    }

    private void beginTranslate(String source, String target) {
        step = "result";
        final int gen = ++generation;
        final String text = selected;
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
        preview.setText(previewOf(selected));
        status.setText(data.optString("note", ""));
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

    private String previewOf(String text) {
        String oneLine = text.replace('\n', ' ').replaceAll(" +", " ").trim();
        if (oneLine.length() > 160) return oneLine.substring(0, 157) + "…";
        return oneLine;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
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
