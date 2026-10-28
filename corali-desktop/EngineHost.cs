// Private console host for the unmodified Cedro CLI (MIT).
// Windows creates this console hidden before Main. Cedro therefore cannot AllocConsole again.
using System;
using System.Diagnostics;
using System.Text;
class EngineHost {
    static string Quote(string s) {
        var b=new StringBuilder("\""); int slashes=0;
        foreach(char c in s) {
            if(c=='\\') { slashes++; continue; }
            if(c=='"') b.Append('\\',slashes*2+1);
            else b.Append('\\',slashes);
            slashes=0; b.Append(c);
        }
        b.Append('\\',slashes*2); b.Append('"'); return b.ToString();
    }
    static int Main(string[] args) {
        Console.OutputEncoding=new UTF8Encoding(false);
        if(args.Length<1) return 2;
        try {
            var command=new StringBuilder();
            for(int i=1;i<args.Length;i++) { if(i>1) command.Append(' '); command.Append(Quote(args[i])); }
            var info=new ProcessStartInfo(args[0],command.ToString());
            info.UseShellExecute=false;
            info.CreateNoWindow=false; // Inherit this already hidden console; do not let Cedro allocate one.
            info.WindowStyle=ProcessWindowStyle.Hidden; // Also hide an explicit AllocConsole in a GUI child.
            info.RedirectStandardOutput=true; info.RedirectStandardError=true; info.RedirectStandardInput=true;
            info.StandardOutputEncoding=new UTF8Encoding(false); info.StandardErrorEncoding=new UTF8Encoding(false);
            using(var process=new Process()) {
                process.StartInfo=info;
                process.OutputDataReceived+=(s,e)=>{if(e.Data!=null)Console.Out.WriteLine(e.Data);};
                process.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)Console.Error.WriteLine(e.Data);};
                process.Start(); process.StandardInput.Close();
                process.BeginOutputReadLine(); process.BeginErrorReadLine();
                process.WaitForExit(); return process.ExitCode;
            }
        } catch(Exception e) { Console.Error.WriteLine(e.Message); return 1; }
    }
}
