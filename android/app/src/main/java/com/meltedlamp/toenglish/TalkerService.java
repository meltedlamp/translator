package com.meltedlamp.toenglish;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;

public class TalkerService extends Service {
    private static final int NOTIFICATION_ID = 41;
    private static final String CHANNEL_ID = "talker";

    private boolean foreground;

    static void start(Context context) {
        Intent service = new Intent(context, TalkerService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(service);
        } else {
            context.startService(service);
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        enterForeground();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        enterForeground();
        return START_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        scheduleRestart();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        if (foreground) scheduleRestart();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void enterForeground() {
        Notification notification = buildNotification();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
        foreground = true;
    }

    private Notification buildNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.talker_channel),
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription(getString(R.string.talker_on_detail));
            channel.setShowBadge(false);
            NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (manager != null) manager.createNotificationChannel(channel);
        }
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pending = PendingIntent.getActivity(
                this,
                0,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setSmallIcon(R.drawable.ic_stat_talker)
                .setContentTitle(getString(R.string.talker_on))
                .setContentText(getString(R.string.talker_on_detail))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(pending)
                .setCategory(Notification.CATEGORY_SERVICE)
                .build();
    }

    private void scheduleRestart() {
        try {
            Intent restart = new Intent(this, TalkerService.class);
            int flags = PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_IMMUTABLE;
            PendingIntent pending = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                    ? PendingIntent.getForegroundService(this, 1, restart, flags)
                    : PendingIntent.getService(this, 1, restart, flags);
            AlarmManager alarms = (AlarmManager) getSystemService(ALARM_SERVICE);
            if (alarms == null) return;
            alarms.set(AlarmManager.ELAPSED_REALTIME, SystemClock.elapsedRealtime() + 1500, pending);
        } catch (Exception ignored) {
        }
    }
}
