package com.shiying.local

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.os.IBinder
import android.os.PersistableBundle
import androidx.core.app.NotificationCompat
import org.json.JSONObject

object DownloadNotice {
    const val ID = 4107
    private const val CHANNEL = "shiying_downloads"
    fun build(context: Context, job: JSONObject): Notification {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "拾影下载进度", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val cancel = PendingIntent.getBroadcast(context, 1, Intent(context, CancelDownloadReceiver::class.java).putExtra("jobId", job.getString("id")), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val album = job.optString("kind") == "album"
        return NotificationCompat.Builder(context, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(job.optString("title").take(80)).setContentText(if (album) "已保存 ${job.optInt("done")}/${job.optInt("total")} 张" else "正在下载到手机")
            .setContentIntent(open).setOnlyAlertOnce(true).setOngoing(true).setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setProgress(if (album) job.optInt("total") else 100, if (album) job.optInt("done") else if (job.optLong("currentTotal") > 0) (job.optLong("currentBytes") * 100 / job.optLong("currentTotal")).toInt() else 0, !album && job.optLong("currentTotal") == 0L)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "取消", cancel).build()
    }
    fun update(context: Context, job: JSONObject) { runCatching { context.getSystemService(NotificationManager::class.java).notify(ID, build(context, job)) } }
    fun remove(context: Context) { context.getSystemService(NotificationManager::class.java).cancel(ID) }
}

object TransferScheduler {
    fun schedule(context: Context, id: String) {
        if (Build.VERSION.SDK_INT >= 34) {
            val extras = PersistableBundle().apply { putString("jobId", id) }
            val info = JobInfo.Builder(4107, ComponentName(context, UserDownloadService::class.java)).setUserInitiated(true)
                .setRequiredNetwork(NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build()).setExtras(extras).build()
            check(context.getSystemService(JobScheduler::class.java).schedule(info) == JobScheduler.RESULT_SUCCESS)
        } else context.startForegroundService(Intent(context, LegacyDownloadService::class.java).putExtra("jobId", id))
    }
}

class UserDownloadService : JobService() {
    private var stopped = false
    override fun onStartJob(params: JobParameters): Boolean {
        if (Build.VERSION.SDK_INT < 34) return false
        stopped = false
        val engine = LocalEngine.of(this)
        val id = params.extras.getString("jobId") ?: return false
        val job = engine.repository.get(id) ?: return false
        setNotification(params, DownloadNotice.ID, DownloadNotice.build(this, job), JOB_END_NOTIFICATION_POLICY_REMOVE)
        return engine.executeTransfer(id) { if (!stopped) jobFinished(params, false); DownloadNotice.remove(this) }
    }
    override fun onStopJob(params: JobParameters): Boolean {
        stopped = true
        params.extras.getString("jobId")?.let { LocalEngine.of(this).stop(it, "interrupted") }
        return false
    }
}

class LegacyDownloadService : Service() {
    private var id: String? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val jobId = intent?.getStringExtra("jobId") ?: return START_NOT_STICKY
        val engine = LocalEngine.of(this)
        val job = engine.repository.get(jobId) ?: return START_NOT_STICKY
        id = jobId
        startForeground(DownloadNotice.ID, DownloadNotice.build(this, job), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (!engine.executeTransfer(jobId) { id = null; stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }) { id = null; stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }
        return START_NOT_STICKY
    }
    override fun onDestroy() { id?.let { LocalEngine.of(this).stop(it, "interrupted") }; super.onDestroy() }
    override fun onBind(intent: Intent?): IBinder? = null
}

class CancelDownloadReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        intent.getStringExtra("jobId")?.let { LocalEngine.of(context).action(it, "cancel") }
    }
}
