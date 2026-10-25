import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Looper;
import java.lang.reflect.Method;
import java.util.List;

/**
 * Tiny app_process helper used by the Packages tab.
 *
 * Prints one "package<TAB>label" line for every installed application.
 * Run it on the device with:
 *
 *   CLASSPATH=/data/local/tmp/adb_manager_labels.dex \
 *       app_process /system/bin DeviceLabels
 */
public class DeviceLabels {
    public static void main(String[] args) {
        try {
            Looper.prepareMainLooper();
            Class<?> atClass = Class.forName("android.app.ActivityThread");
            Method systemMain = atClass.getDeclaredMethod("systemMain");
            systemMain.setAccessible(true);
            Object thread = systemMain.invoke(null);
            Method getSystemContext = atClass.getDeclaredMethod("getSystemContext");
            getSystemContext.setAccessible(true);
            Context ctx = (Context) getSystemContext.invoke(thread);
            PackageManager pm = ctx.getPackageManager();
            List<ApplicationInfo> apps = pm.getInstalledApplications(PackageManager.GET_META_DATA);
            for (ApplicationInfo ai : apps) {
                CharSequence label = pm.getApplicationLabel(ai);
                String value = label == null ? "" : label.toString();
                value = value.replace("\t", " ").replace("\r", " ").replace("\n", " ");
                System.out.println(ai.packageName + "\t" + value);
            }
        } catch (Throwable t) {
            t.printStackTrace(System.err);
            System.exit(1);
        }
    }
}
