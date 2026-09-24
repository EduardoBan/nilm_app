using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Reflection;

internal static class NilmInstaller
{
    private const string PayloadFileName = "NILM_Energy_Platform.zip";

    private static string logPath = Path.Combine(Path.GetTempPath(), "nilm_installer.log");

    private static void Log(string message)
    {
        try { File.AppendAllText(logPath, DateTime.Now.ToString("s") + " " + message + Environment.NewLine); }
        catch { }
    }

    public static int Main()
    {
        try { File.Delete(logPath); } catch { }
        Log("inicio");
        string target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs", "NILM_Energy_Platform");
        Log("target=" + target);
        Log("payload=" + PayloadFileName);
        string label = Path.Combine(target, "backend", "load_labels.json");
        string preservedLabel = null;
        try
        {
            if (File.Exists(label))
            {
                preservedLabel = Path.Combine(Path.GetTempPath(), "nilm_labels_" + Guid.NewGuid().ToString("N") + ".json");
                File.Copy(label, preservedLabel, true);
                Log("labels_preservados");
            }

            Directory.CreateDirectory(target);
            Log("target_creado");
            string sourceDirectory = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string adjacentPayload = Path.Combine(sourceDirectory, PayloadFileName);
            if (File.Exists(adjacentPayload))
            {
                Log("payload_path=" + adjacentPayload);
                ExtractPayload(adjacentPayload, target);
            }
            else
            {
                Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadFileName);
                if (payload == null)
                    throw new FileNotFoundException("El instalador no contiene el payload integrado", PayloadFileName);
                Log("payload_embedded=1");
                using (payload)
                    ExtractStream(payload, target);
            }
            Log("payload_extraido");
            if (preservedLabel != null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(label));
                File.Copy(preservedLabel, label, true);
            }
            foreach (string name in new[] { "Data", "cache", "reports" })
                Directory.CreateDirectory(Path.Combine(target, name));

            CreateShortcut(target);
            Log("acceso_directo_procesado");
            Console.WriteLine("Instalacion completada en: " + target);
            Console.WriteLine("Use NILM_Platform.cmd para iniciar la aplicacion.");
            return 0;
        }
        catch (Exception ex)
        {
            Log("ERROR " + ex);
            Console.Error.WriteLine("Error instalando NILM Energy Platform: " + ex.Message);
            return 1;
        }
        finally
        {
            if (preservedLabel != null) { try { File.Delete(preservedLabel); } catch { } }
        }
    }

    private static void ExtractPayload(string payloadPath, string target)
    {
        using (FileStream input = File.OpenRead(payloadPath))
            ExtractStream(input, target);
    }

    private static void ExtractStream(Stream input, string target)
    {
        using (ZipArchive archive = new ZipArchive(input, ZipArchiveMode.Read, false))
        {
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                if (relative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(relative))
                    throw new InvalidDataException("Entrada no segura en el payload: " + entry.FullName);
                string destination = Path.Combine(target, relative);
                if (entry.FullName.EndsWith("/", StringComparison.Ordinal) || entry.FullName.EndsWith("\\", StringComparison.Ordinal))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(destination));
                using (Stream source = entry.Open())
                using (FileStream output = File.Create(destination))
                    source.CopyTo(output);
            }
        }
    }

    private static void CreateShortcut(string target)
    {
        try
        {
            string menu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "Microsoft", "Windows", "Start Menu", "Programs", "NILM");
            Directory.CreateDirectory(menu);
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            object shell = Activator.CreateInstance(shellType);
            object link = shellType.InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { Path.Combine(menu, "NILM Energy Platform.lnk") });
            Type linkType = link.GetType();
            linkType.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, link, new object[] { Path.Combine(target, "NILM_Platform.cmd") });
            linkType.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, link, new object[] { target });
            linkType.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, link, new object[] { "NILM Energy Analytics Platform" });
            linkType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, link, null);
        }
        catch
        {
            // El acceso directo es opcional; la instalacion sigue siendo valida.
        }
    }
}
