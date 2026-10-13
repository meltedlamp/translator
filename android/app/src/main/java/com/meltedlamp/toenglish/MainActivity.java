package com.meltedlamp.toenglish;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final int NOTIFICATION_PERMISSION = 41;

    private WebView webView;
    private boolean pageReady;
    private String pendingShare;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Translator.loadNames(getAssets());
        webView = new WebView(this);
        setContentView(webView);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                pageReady = true;
                deliverShare();
            }
        });
        webView.addJavascriptInterface(new NativeBridge(webView), "ToEnglishNative");
        pendingShare = textFrom(getIntent());
        webView.loadUrl("file:///android_asset/www/index.html");
        stayOn();
    }

    private void stayOn() {
        TalkerService.start(this);
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.POST_NOTIFICATIONS},
                    NOTIFICATION_PERMISSION);
            return;
        }
        askToIgnoreBattery();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == NOTIFICATION_PERMISSION) {
            TalkerService.start(this);
            askToIgnoreBattery();
        }
    }

    private void askToIgnoreBattery() {
        if (!Intent.ACTION_MAIN.equals(getIntent() == null ? null : getIntent().getAction())) return;
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return;
        PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
        if (power == null || power.isIgnoringBatteryOptimizations(getPackageName())) return;
        Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
        intent.setData(Uri.parse("package:" + getPackageName()));
        try {
            startActivity(intent);
        } catch (Exception ignored) {
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        pendingShare = textFrom(intent);
        if (pageReady) deliverShare();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    private String textFrom(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return null;
        String text = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (text == null || text.trim().isEmpty()) return null;
        return text;
    }

    private void deliverShare() {
        if (pendingShare == null || webView == null) return;
        String script = "window.receiveSharedText(" + JSONObject.quote(pendingShare) + ")";
        pendingShare = null;
        webView.evaluateJavascript(script, null);
    }
}
