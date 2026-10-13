package com.meltedlamp.toenglish;

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
}
