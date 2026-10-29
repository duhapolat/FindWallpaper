// FindWallpaper.exe — kurulu uygulamanın başlatıcısı.
// Windows'ta hazır gelen .NET Framework derleyicisiyle (csc.exe) derlenir, ek bir şey gerektirmez.
//
//   FindWallpaper.exe                          -> arayüzü açar (app.py)
//   FindWallpaper.exe video.mp4 --stil manzara -> komut satırı (bul.py); videoyu exe'nin üstüne sürüklemek de olur

using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

static class Launcher
{
    [STAThread]
    static int Main(string[] args)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string py = Path.Combine(baseDir, "python", "python.exe");
        string appDir = Path.Combine(baseDir, "app");
        bool cli = args.Length > 0;
        string script = Path.Combine(appDir, cli ? "bul.py" : "app.py");

        if (!File.Exists(py) || !File.Exists(script) || !Directory.Exists(Path.Combine(baseDir, "python", "Lib", "site-packages", "torch")))
        {
            MessageBox.Show("Kurulum tamamlanmamış görünüyor.\n\nKurulum dosyasını (FindWallpaper-Setup) tekrar çalıştır. " +
                            "Ayrıntılar: " + Path.Combine(baseDir, "kurulum.log"),
                            "FindWallpaper", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        try { Console.OutputEncoding = Encoding.UTF8; } catch { }
        Console.Title = "FindWallpaper";

        var sb = new StringBuilder(Quote(script));
        foreach (string a in args) sb.Append(' ').Append(Quote(a));

        var psi = new ProcessStartInfo(py, sb.ToString());
        psi.UseShellExecute = false;
        psi.WorkingDirectory = appDir;
        string ffmpegDir = Path.Combine(baseDir, "ffmpeg");
        psi.EnvironmentVariables["PATH"] = ffmpegDir + ";" + Environment.GetEnvironmentVariable("PATH");
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";
        psi.EnvironmentVariables["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1";
        string pictures = Environment.GetFolderPath(Environment.SpecialFolder.MyPictures);
        string videos = Environment.GetFolderPath(Environment.SpecialFolder.MyVideos);
        psi.EnvironmentVariables["FINDWALLPAPER_OUT"] = Path.Combine(pictures, "FindWallpaper");
        psi.EnvironmentVariables["FINDWALLPAPER_DOWNLOADS"] = Path.Combine(videos, "FindWallpaper");

        if (!cli)
        {
            Console.WriteLine("FindWallpaper açılıyor... Birkaç saniye içinde tarayıcıda açılacak.");
            Console.WriteLine("Bulunan kareler: " + Path.Combine(pictures, "FindWallpaper"));
            Console.WriteLine("Programı kapatmak için bu pencereyi kapat.\n");
        }

        Process p = Process.Start(psi);
        p.WaitForExit();
        if (p.ExitCode != 0)
        {
            Console.WriteLine("\nBir hata oluştu (kod " + p.ExitCode + "). Kapatmak için Enter'a bas.");
            Console.ReadLine();
        }
        return p.ExitCode;
    }

    // Windows komut satırı kurallarına göre argümanı tırnak içine alır
    static string Quote(string arg)
    {
        if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return arg;
        var sb = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char c in arg)
        {
            if (c == '\\') { backslashes++; continue; }
            if (c == '"') sb.Append('\\', backslashes * 2 + 1);
            else sb.Append('\\', backslashes);
            backslashes = 0;
            sb.Append(c);
        }
        sb.Append('\\', backslashes * 2).Append('"');
        return sb.ToString();
    }
}
