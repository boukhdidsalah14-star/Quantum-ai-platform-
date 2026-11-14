package com.quantumai.trading;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.os.Build;
import android.os.IBinder;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SignalOverlayService extends Service {
    private static final String CHANNEL = "quantum_signal_overlay";
    private static final int NOTIFICATION_ID = 6201;
    private static final String BASE = "https://quantum-ai-platform-62cz.onrender.com";
    private WindowManager windowManager;
    private View bubble;
    private View panel;
    private Spinner assetPicker;
    private Spinner timeframePicker;
    private TextView resultText;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startForeground(NOTIFICATION_ID, buildNotification());
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        showBubble();
    }

    private int dp(float value) { return (int)(value * getResources().getDisplayMetrics().density + 0.5f); }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "QUANTUM AI floating signals", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keeps the floating signal chat head available over other apps when enabled.");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0));
        if (Build.VERSION.SDK_INT >= 26) {
            return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("QUANTUM AI floating signals")
                .setContentText("Tap the Q bubble over any app to request a market signal.")
                .setContentIntent(pending).setOngoing(true).build();
        }
        return new Notification.Builder(this)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("QUANTUM AI floating signals")
            .setContentText("Floating signal assistant is active.")
            .setContentIntent(pending).setOngoing(true).build();
    }

    private WindowManager.LayoutParams overlayParams(int width, int height, int flags, int gravity) {
        int type = Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;
        return new WindowManager.LayoutParams(width, height, type, flags, PixelFormat.TRANSLUCENT, gravity);
    }

    private void showBubble() {
        if (bubble != null) return;
        TextView chip = new TextView(this);
        chip.setText("Q");
        chip.setTextColor(Color.WHITE);
        chip.setTextSize(23);
        chip.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        chip.setGravity(Gravity.CENTER);
        chip.setBackground(makeCircle());
        chip.setElevation(dp(9));
        bubble = chip;
        WindowManager.LayoutParams params = overlayParams(dp(58), dp(58), WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN, Gravity.TOP | Gravity.START);
        params.x = dp(14); params.y = dp(220);
        windowManager.addView(bubble, params);
        chip.setOnTouchListener(new View.OnTouchListener() {
            float downX, downY; int startX, startY; boolean moved;
            @Override public boolean onTouch(View view, MotionEvent event) {
                WindowManager.LayoutParams p = (WindowManager.LayoutParams) view.getLayoutParams();
                if (event.getAction() == MotionEvent.ACTION_DOWN) {
                    downX = event.getRawX(); downY = event.getRawY(); startX = p.x; startY = p.y; moved = false; return true;
                }
                if (event.getAction() == MotionEvent.ACTION_MOVE) {
                    float dx = event.getRawX() - downX, dy = event.getRawY() - downY;
                    if (Math.abs(dx) + Math.abs(dy) > dp(5)) moved = true;
                    if (moved) { p.x = startX + (int)dx; p.y = startY + (int)dy; windowManager.updateViewLayout(view, p); }
                    return true;
                }
                if (event.getAction() == MotionEvent.ACTION_UP) { if (!moved) togglePanel(); return true; }
                return false;
            }
        });
    }

    private android.graphics.drawable.GradientDrawable makeCircle() {
        android.graphics.drawable.GradientDrawable d = new android.graphics.drawable.GradientDrawable();
        d.setShape(android.graphics.drawable.GradientDrawable.OVAL);
        d.setColor(Color.rgb(8, 76, 145));
        d.setStroke(dp(2), Color.rgb(103, 220, 255));
        return d;
    }

    private android.graphics.drawable.GradientDrawable makePanelBackground() {
        android.graphics.drawable.GradientDrawable d = new android.graphics.drawable.GradientDrawable();
        d.setColor(Color.rgb(5, 17, 34));
        d.setCornerRadius(dp(18));
        d.setStroke(dp(1), Color.rgb(45, 133, 199));
        return d;
    }

    private TextView text(String value, int size, boolean bold) {
        TextView t = new TextView(this); t.setText(value); t.setTextColor(Color.rgb(232, 245, 255)); t.setTextSize(size);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        t.setPadding(dp(4), dp(6), dp(4), dp(6)); return t;
    }

    private void togglePanel() { if (panel == null) showPanel(); else hidePanel(); }

    private void showPanel() {
        if (panel != null) return;
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(14), dp(12), dp(14), dp(14)); root.setBackground(makePanelBackground());
        LinearLayout header = new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL); header.setOrientation(LinearLayout.HORIZONTAL);
        TextView title = text("QUANTUM AI", 17, true); title.setTextColor(Color.rgb(82, 190, 255));
        Button close = new Button(this); close.setText("×"); close.setTextSize(19); close.setTextColor(Color.WHITE); close.setBackgroundColor(Color.TRANSPARENT);
        header.addView(title, new LinearLayout.LayoutParams(0, dp(42), 1)); header.addView(close, new LinearLayout.LayoutParams(dp(44), dp(42))); root.addView(header);
        root.addView(text("FLOATING SIGNAL ASSISTANT", 9, true));
        root.addView(text("Choose a market and timeframe. The assistant returns analysis only; it never places an order.", 11, false));
        assetPicker = new Spinner(this);
        String[] assets = {"EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "BTC/USDT", "ETH/USDT"};
        assetPicker.setAdapter(new ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item, assets));
        root.addView(assetPicker, new LinearLayout.LayoutParams(-1, dp(46)));
        timeframePicker = new Spinner(this);
        timeframePicker.setAdapter(new ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item, new String[]{"5m", "15m", "1h"}));
        root.addView(timeframePicker, new LinearLayout.LayoutParams(-1, dp(46)));
        Button analyze = new Button(this); analyze.setText("GET SIGNAL"); analyze.setTextColor(Color.WHITE); analyze.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(14, 113, 204)));
        LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(-1, dp(48)); buttonParams.topMargin = dp(8); root.addView(analyze, buttonParams);
        resultText = text("READY · Choose an asset and request a signal.", 12, false); resultText.setBackgroundColor(Color.rgb(8, 29, 53)); root.addView(resultText);
        Button open = new Button(this); open.setText("OPEN QUANTUM AI"); open.setTextColor(Color.rgb(166, 219, 255)); open.setBackgroundColor(Color.TRANSPARENT); root.addView(open);
        panel = root;
        WindowManager.LayoutParams params = overlayParams(dp(310), -2, WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL, Gravity.TOP | Gravity.START);
        params.x = dp(12); params.y = dp(90);
        windowManager.addView(panel, params);
        close.setOnClickListener(v -> hidePanel());
        analyze.setOnClickListener(v -> requestSignal());
        open.setOnClickListener(v -> { Intent i = new Intent(this, MainActivity.class); i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP); startActivity(i); });
    }

    private void hidePanel() {
        if (panel != null) { try { windowManager.removeView(panel); } catch (Exception ignored) {} panel = null; }
    }

    private void requestSignal() {
        if (assetPicker == null || resultText == null) return;
        String asset = String.valueOf(assetPicker.getSelectedItem());
        String timeframe = String.valueOf(timeframePicker.getSelectedItem());
        final boolean crypto = asset.contains("USDT");
        final String symbol = crypto ? asset.replace("/", "") : "frx" + asset.replace("/", "");
        final String interval = crypto && !timeframe.equals("1h") ? "1h" : timeframe;
        resultText.setText("ANALYZING · Fetching completed candles…");
        executor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                String path = crypto
                    ? "/api/signals/crypto/" + symbol + "?source=binance&timeframe=" + interval
                    : "/api/signals/deriv/" + symbol + "?category=forex&timeframe=" + timeframe;
                URL url = new URL(BASE + path);
                connection = (HttpURLConnection)url.openConnection(); connection.setRequestMethod("GET"); connection.setConnectTimeout(10000); connection.setReadTimeout(15000);
                int code = connection.getResponseCode();
                BufferedReader reader = new BufferedReader(new InputStreamReader(code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream()));
                StringBuilder body = new StringBuilder(); String line; while ((line = reader.readLine()) != null) body.append(line); reader.close();
                JSONObject json = new JSONObject(body.toString());
                if (code < 200 || code >= 300) throw new Exception(json.optString("detail", "Market analysis unavailable"));
                String direction = json.optString("direction", "WAIT");
                String trend = json.optString("trend", "—");
                String rsi = json.has("rsi_14") ? json.optString("rsi_14") : "—";
                String strength = json.optString("signal_strength", "—");
                JSONArray reasons = json.optJSONArray("reasons");
                StringBuilder message = new StringBuilder(direction + " · " + asset + " · " + timeframe + "\nTrend: " + trend + " · RSI: " + rsi + "\nStrength: " + strength + "\n");
                if (reasons != null) for (int i = 0; i < Math.min(3, reasons.length()); i++) message.append("• ").append(reasons.optString(i)).append("\n");
                message.append("Analysis only · no order placed.");
                String output = message.toString();
                runOnUiThread(() -> { if (resultText != null) resultText.setText(output); });
            } catch (Exception e) {
                String error = "WAIT · " + (e.getMessage() == null ? "Analysis unavailable" : e.getMessage());
                runOnUiThread(() -> { if (resultText != null) resultText.setText(error); });
            } finally { if (connection != null) connection.disconnect(); }
        });
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) { return START_STICKY; }
    @Override public void onDestroy() {
        hidePanel();
        if (bubble != null) { try { windowManager.removeView(bubble); } catch (Exception ignored) {} bubble = null; }
        executor.shutdownNow();
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
