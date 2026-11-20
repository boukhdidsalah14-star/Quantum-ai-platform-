package com.quantumai.trading;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.os.*;
import android.view.*;
import android.view.Gravity;
import android.widget.*;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FloatingAssistantService extends Service {
    public static final String ACTION_START = "com.quantumai.trading.FLOAT_START";
    public static final String ACTION_STOP = "com.quantumai.trading.FLOAT_STOP";
    private static final String API = "https://quantum-ai-iqoption-preview.onrender.com";
    private final String[] symbols = {"frxEURUSD","frxGBPUSD","frxUSDJPY","frxAUDUSD","frxUSDCAD","frxUSDCHF","frxEURJPY","frxGBPJPY"};
    private final String[] pairs = {"EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","USD/CHF","EUR/JPY","GBP/JPY"};
    private final String[] expiries = {"1","5","15","30","60"};
    private final String[] expiryLabels = {"1 minute","5 minutes","15 minutes","30 minutes","60 minutes"};
    private WindowManager wm;
    private View bubble, panel;
    private WindowManager.LayoutParams bubbleParams, panelParams;
    private TextView bubbleText, resultText, countdownText;
    private Spinner pairSpinner, expirySpinner;
    private Button signalButton;
    private Handler handler = new Handler(Looper.getMainLooper());
    private ExecutorService executor = Executors.newSingleThreadExecutor();
    private long expiryAt = 0;
    private String lastDirection = "WAIT";
    private Runnable timer;
    private int bubbleColor = Color.rgb(20,145,230);
    private boolean destroyed = false;

    @Override public void onCreate() {
        super.onCreate();
        wm = (WindowManager)getSystemService(WINDOW_SERVICE);
        createChannel();
        startForeground(77, buildNotification());
        showBubble();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) { getSharedPreferences("quantum_assistant", MODE_PRIVATE).edit().putBoolean("enabled", false).apply(); stopSelf(); return START_NOT_STICKY; }
        return START_STICKY;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel("quantum_overlay","QUANTUM AI Floating Assistant",NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keeps the optional floating signal assistant available over other apps.");
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }

    private Notification buildNotification() {
        Intent stop = new Intent(this, FloatingAssistantService.class).setAction(ACTION_STOP);
        PendingIntent pending = PendingIntent.getService(this, 78, stop, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this,"quantum_overlay") : new Notification.Builder(this);
        return b.setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("QUANTUM AI is ready")
                .setContentText("Floating signal assistant is active. Tap the circle to open it.")
                .setOngoing(true).addAction(android.R.drawable.ic_menu_close_clear_cancel,"Stop",pending).build();
    }

    private WindowManager.LayoutParams params(int width, int height, int gravity) {
        int type = Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(width,height,type, WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT);
        p.gravity = gravity;
        return p;
    }

    private TextView text(String value, int size, int color) {
        TextView t = new TextView(this); t.setText(value); t.setTextColor(color); t.setTextSize(size);
        t.setGravity(Gravity.CENTER); t.setPadding(dp(8),dp(6),dp(8),dp(6)); return t;
    }
    private int dp(float v) { return (int)(v * getResources().getDisplayMetrics().density + .5f); }

    private void showBubble() {
        if (bubble != null || destroyed) return;
        bubbleText = text("ϟ",25,Color.WHITE); bubbleText.setTypeface(null,Typeface.BOLD);
        bubbleText.setBackground(round(bubbleColor,dp(30)));
        bubble = bubbleText;
        bubbleParams = params(dp(58),dp(58),Gravity.TOP|Gravity.START);
        bubbleParams.x = dp(14); bubbleParams.y = dp(180);
        bubbleText.setOnClickListener(v -> togglePanel());
        bubbleText.setOnTouchListener(new View.OnTouchListener() {
            float downX,downY; int startX,startY; boolean moved;
            public boolean onTouch(View v, android.view.MotionEvent e) {
                if(e.getAction()==MotionEvent.ACTION_DOWN){downX=e.getRawX();downY=e.getRawY();startX=bubbleParams.x;startY=bubbleParams.y;moved=false;return true;}
                if(e.getAction()==MotionEvent.ACTION_MOVE){float dx=e.getRawX()-downX,dy=e.getRawY()-downY;if(Math.abs(dx)+Math.abs(dy)>dp(7))moved=true;if(moved){bubbleParams.x=startX+(int)dx;bubbleParams.y=startY+(int)dy;wm.updateViewLayout(bubble,bubbleParams);}return true;}
                if(e.getAction()==MotionEvent.ACTION_UP){if(!moved)togglePanel();return true;}return true;
            }
        });
        try { wm.addView(bubble,bubbleParams); } catch(Exception e) {
            bubble=null;
            Toast.makeText(this, "Could not display the floating circle. Check Android display-over-other-apps permission.", Toast.LENGTH_LONG).show();
            stopSelf();
        }
    }

    private android.graphics.drawable.GradientDrawable round(int color,int radius) {
        android.graphics.drawable.GradientDrawable d=new android.graphics.drawable.GradientDrawable();
        d.setColor(color);d.setCornerRadius(radius);d.setStroke(dp(1),Color.argb(170,110,205,255));return d;
    }

    private android.graphics.drawable.GradientDrawable rainbow() {
        android.graphics.drawable.GradientDrawable d = new android.graphics.drawable.GradientDrawable(
                android.graphics.drawable.GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{Color.RED, 0xFFFF9800, Color.YELLOW, Color.GREEN, Color.CYAN, 0xFF3F51B5, 0xFF9C27B0});
        d.setCornerRadius(dp(30)); d.setStroke(dp(1), Color.WHITE); return d;
    }

    private void togglePanel() { if(panel==null) showPanel(); else hidePanel(); }

    private void showPanel() {
        if(panel!=null)return;
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(14),dp(12),dp(14),dp(12));
        root.setBackground(round(Color.rgb(5,18,36),dp(18)));
        LinearLayout head=new LinearLayout(this);head.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=text("QUANTUM AI  ·  FLOATING SIGNAL",13,Color.rgb(90,205,255));title.setTypeface(null,Typeface.BOLD);title.setGravity(Gravity.CENTER_VERTICAL|Gravity.LEFT);
        TextView close=text("×",24,Color.WHITE);close.setOnClickListener(v->hidePanel());
        head.addView(title,new LinearLayout.LayoutParams(0,dp(38),1));head.addView(close,new LinearLayout.LayoutParams(dp(38),dp(38)));root.addView(head);
        root.addView(text("FOREX PAIR",10,Color.LTGRAY));
        pairSpinner=new Spinner(this);pairSpinner.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,pairs));root.addView(pairSpinner);
        root.addView(text("EXPIRY",10,Color.LTGRAY));
        expirySpinner=new Spinner(this);expirySpinner.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,expiryLabels));expirySpinner.setSelection(1);root.addView(expirySpinner);
        signalButton=new Button(this);signalButton.setText("GENERATE SIGNAL");signalButton.setTextColor(Color.WHITE);signalButton.setBackground(round(Color.rgb(20,112,210),dp(12)));root.addView(signalButton);
        resultText=text("Choose a pair and generate a signal.",14,Color.WHITE);root.addView(resultText);
        countdownText=text("Signals are analysis only · No broker orders are placed.",10,Color.LTGRAY);root.addView(countdownText);
        LinearLayout outcomes=new LinearLayout(this);outcomes.setOrientation(LinearLayout.HORIZONTAL);
        Button win=outcomeButton("WIN",Color.rgb(15,165,90));Button loss=outcomeButton("LOSS",Color.rgb(205,45,55));Button draw=outcomeButton("DRAW",Color.rgb(145,65,190));
        win.setOnClickListener(v->setOutcome("WIN",Color.rgb(15,165,90)));loss.setOnClickListener(v->setOutcome("LOSS",Color.rgb(205,45,55)));draw.setOnClickListener(v->setOutcome("DRAW",Color.rgb(145,65,190)));
        outcomes.addView(win,new LinearLayout.LayoutParams(0,dp(42),1));outcomes.addView(loss,new LinearLayout.LayoutParams(0,dp(42),1));outcomes.addView(draw,new LinearLayout.LayoutParams(0,dp(42),1));root.addView(outcomes);
        TextView note=text("After expiry, tap WIN, LOSS or DRAW to update the circle. IQ Option is not connected.",10,Color.GRAY);root.addView(note);
        signalButton.setOnClickListener(v->generateSignal());
        panel=root;panelParams=params(dp(300),WindowManager.LayoutParams.WRAP_CONTENT,Gravity.TOP|Gravity.START);
        panelParams.flags = WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL;
        panelParams.x=Math.max(dp(8),bubbleParams.x-dp(115));panelParams.y=Math.max(dp(45),bubbleParams.y+dp(66));
        try{wm.addView(panel,panelParams);}catch(Exception e){
            panel=null;
            Toast.makeText(this, "Could not open the assistant panel. Try moving the circle away from the screen edge.", Toast.LENGTH_SHORT).show();
        }
    }

    private Button outcomeButton(String label,int color){Button b=new Button(this);b.setText(label);b.setTextSize(11);b.setTextColor(Color.WHITE);b.setBackground(round(color,dp(9)));return b;}

    private void hidePanel(){if(panel!=null){try{wm.removeView(panel);}catch(Exception ignored){}panel=null;}}

    private void generateSignal() {
        if (expiryAt > System.currentTimeMillis()) {
            countdownText.setText("A signal is already active. Wait for expiry and record its result first.");
            return;
        }
        if(signalButton!=null)signalButton.setEnabled(false);
        final int selected=pairSpinner.getSelectedItemPosition();
        final int minutes=Integer.parseInt(expiries[expirySpinner.getSelectedItemPosition()]);
        final String timeframe=minutes==60?"1h":minutes+"m";
        resultText.setText("Analysing public market data…");
        countdownText.setText("Loading completed candles for "+timeframe);
        executor.execute(()->{
            String message;
            String direction="WAIT";
            long nextExpiry=0;
            try{
                URL url=new URL(API+"/api/signals/forex/"+symbols[selected]+"?timeframe="+timeframe);
                HttpURLConnection connection=(HttpURLConnection)url.openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(12000);
                connection.setReadTimeout(12000);
                int status=connection.getResponseCode();
                java.io.InputStream stream=status>=200&&status<300?connection.getInputStream():connection.getErrorStream();
                String body;
                try(java.util.Scanner scanner=new java.util.Scanner(stream,"UTF-8").useDelimiter("\\A")){
                    body=scanner.hasNext()?scanner.next():"{}";
                }
                connection.disconnect();
                JSONObject json=new JSONObject(body);
                if(status<200||status>=300){
                    message=json.optString("detail","Market data is temporarily unavailable.");
                }else{
                    direction=json.optString("direction","WAIT").toUpperCase();
                    String strength=json.optString("signal_strength","low").toUpperCase();
                    String trend=json.optString("trend","NEUTRAL");
                    double price=json.optDouble("last_close",Double.NaN);
                    int score=json.optInt("score",0);
                    StringBuilder details=new StringBuilder();
                    org.json.JSONArray reasons=json.optJSONArray("reasons");
                    if(reasons!=null){
                        for(int i=0;i<Math.min(2,reasons.length());i++){
                            details.append("
• ").append(reasons.optString(i));
                        }
                    }
                    message=pairs[selected]+"  ·  "+direction+
                            "
Strength: "+strength+"  |  Trend: "+trend+
                            "
Score: "+score+"  |  Expiry: "+minutes+" min"+
                            (Double.isNaN(price)?"":"
Last completed close: "+price)+details;
                    if(direction.equals("CALL")||direction.equals("PUT")){
                        nextExpiry=System.currentTimeMillis()+minutes*60_000L;
                    }else{
                        direction="WAIT";
                        message+="
No trade: conditions did not meet the signal filter.";
                    }
                }
            }catch(Exception e){
                message="Signal unavailable. Check your connection and try again.";
                direction="WAIT";
            }
            final String finalDirection=direction;
            final String finalMessage=message;
            final long finalExpiry=nextExpiry;
            handler.post(()->{
                if(signalButton!=null)signalButton.setEnabled(true);
                lastDirection=finalDirection;
                resultText.setText(finalMessage);
                if(finalDirection.equals("CALL"))bubbleText.setText("↑");
                else if(finalDirection.equals("PUT"))bubbleText.setText("↓");
                else bubbleText.setText("ϟ");
                bubbleColor=finalDirection.equals("WAIT")?Color.rgb(20,112,170):Color.rgb(20,145,230);
                bubbleText.setBackground(round(bubbleColor,dp(30)));
                expiryAt=finalExpiry;
                if(expiryAt>0)startCountdown();
                else countdownText.setText("No active expiry. Wait for a CALL or PUT signal.");
            });
        });
    }

    private void startCountdown(){
        if(timer!=null)handler.removeCallbacks(timer);
        timer=new Runnable(){public void run(){
            long left=expiryAt-System.currentTimeMillis();
            if(left<=0){countdownText.setText("EXPIRY REACHED · Confirm your result below");return;}
            long sec=left/1000;countdownText.setText(String.format(java.util.Locale.US,"Time remaining %02d:%02d",sec/60,sec%60));
            handler.postDelayed(this,1000);
        }};handler.post(timer);
    }

    private void setOutcome(String outcome,int color){
        if(expiryAt==0){countdownText.setText("Generate a signal first.");return;}
        if(System.currentTimeMillis()<expiryAt){countdownText.setText("Wait until the selected expiry before recording the result.");return;}
        bubbleColor=color;
        if(outcome.equals("DRAW")) bubbleText.setBackground(rainbow());
        else bubbleText.setBackground(round(color,dp(30)));
        bubbleText.setText(outcome.equals("WIN")?"✓":outcome.equals("LOSS")?"×":"✦");
        resultText.setText(resultText.getText()+"
RESULT: "+outcome+" (confirmed by you)");
        countdownText.setText("Result saved on this device. Generate another signal when ready.");
        expiryAt=0;if(timer!=null)handler.removeCallbacks(timer);
    }

    @Override public void onDestroy(){
        destroyed=true;if(timer!=null)handler.removeCallbacks(timer);hidePanel();
        if(bubble!=null){try{wm.removeView(bubble);}catch(Exception ignored){}bubble=null;}
        if(executor!=null)executor.shutdownNow();stopForeground(true);super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent){return null;}
}
