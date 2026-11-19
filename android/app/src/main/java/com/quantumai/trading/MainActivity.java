package com.quantumai.trading;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.os.Build;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;
import android.Manifest;
import android.content.pm.PackageManager;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final String HOME = "https://quantum-ai-iqoption-preview.onrender.com/";
    private static final int OVERLAY_PERMISSION_REQUEST = 7104;
    private WebView webView;
    private boolean askedOverlay = false;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(android.graphics.Color.rgb(2, 9, 22));
        getWindow().setNavigationBarColor(android.graphics.Color.rgb(2, 9, 22));
        webView = new WebView(this);
        setContentView(webView);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, false);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
                if (host.equals("quantum-ai-iqoption-preview.onrender.com")) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) {}
                return true;
            }
        });
        if (savedInstanceState == null) webView.loadUrl(HOME);
        else webView.restoreState(savedInstanceState);
    }

    @Override protected void onResume() {
        super.onResume();
        if (!askedOverlay && Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) {
            askedOverlay = true;
            new AlertDialog.Builder(this)
                .setTitle("Enable QUANTUM AI floating assistant?")
                .setMessage("You can use the signal circle over IQ Option or Chrome. Android requires your permission to display it over other apps. You can skip this and enable it later.")
                .setPositiveButton("ENABLE", (dialog, which) -> {
                    Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
                    startActivityForResult(intent, OVERLAY_PERMISSION_REQUEST);
                })
                .setNegativeButton("NOT NOW", (dialog, which) -> {})
                .show();
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == OVERLAY_PERMISSION_REQUEST) {
            if (Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(this)) {
                startFloatingAssistant();
            } else {
                Toast.makeText(this, "Overlay permission was not granted. The QUANTUM AI app still works normally.", Toast.LENGTH_LONG).show();
            }
        }
    }

    private void startFloatingAssistant() {
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) return;
        Intent service = new Intent(this, FloatingAssistantService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        Toast.makeText(this, "Floating assistant enabled. Open IQ Option or Chrome and tap the QUANTUM circle.", Toast.LENGTH_LONG).show();
    }

    @Override protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) webView.saveState(outState);
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (webView != null) { webView.destroy(); webView = null; }
        super.onDestroy();
    }
}
