package com.meltedlamp.toenglish;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

final class NativeBridge {
    private final WebView webView;
    private final ExecutorService pool = Executors.newSingleThreadExecutor();

    NativeBridge(WebView webView) {
        this.webView = webView;
    }

    @JavascriptInterface
    public void translate(String id, String text) {
        translate(id, text, "auto", "en");
    }

    @JavascriptInterface
    public void translate(String id, String text, String source, String target) {
        pool.execute(() -> {
            String payload;
            try {
                payload = Translator.translate(text, source, target);
            } catch (Exception ex) {
                payload = "{\"error\":\"Could not reach the translator. Check your connection and try again.\"}";
            }
            String script = "window.onToEnglishResult("
                    + JSONObject.quote(id == null ? "" : id)
                    + ","
                    + JSONObject.quote(payload)
                    + ")";
            webView.post(() -> webView.evaluateJavascript(script, null));
        });
    }

    @JavascriptInterface
    public String brainStatus() {
        return Brain.status().toString();
    }

    @JavascriptInterface
    public String teach(String before, String after) {
        return Brain.teach(before, after).toString();
    }

    @JavascriptInterface
    public void saveLanguages(String source, String target) {
        ProcessTextActivity.storeLanguages(webView.getContext(), source, target);
    }

    @JavascriptInterface
    public String languageSettings() {
        Context context = webView.getContext();
        JSONObject data = new JSONObject();
        try {
            data.put("source", ProcessTextActivity.savedSource(context));
            data.put("target", ProcessTextActivity.savedTarget(context));
            data.put("chosen", ProcessTextActivity.languagesChosen(context));
        } catch (Exception ignored) {
        }
        return data.toString();
    }

    @JavascriptInterface
    public void openSideSetting() {
        Context context = webView.getContext();
        webView.post(() -> {
            ComponentName component = new ComponentName(context, SideTranslateService.class);
            Intent details = new Intent("android.settings.ACCESSIBILITY_DETAILS_SETTINGS");
            details.putExtra("android.intent.extra.COMPONENT_NAME", component.flattenToString());
            details.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                context.startActivity(details);
            } catch (Exception ex) {
                Intent list = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
                list.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try {
                    context.startActivity(list);
                } catch (Exception ignored) {
                }
            }
        });
    }
}
