// Compile explicitly for ARM64. AnyCPU selected the emulated x64 CLR on this Surface.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
[assembly:System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8.1")]

class NativeHost : Form {
    WebView2 browser=new WebView2();
    TcpListener bridge;
    Process backend;
    string secret=Guid.NewGuid().ToString("N")+Guid.NewGuid().ToString("N");
    string data,origin,backendToken;
    volatile bool closing=false;
    static JavaScriptSerializer Json(){return new JavaScriptSerializer();}
    NativeHost(){
        Text="Coralì Lab — Il tuo laboratorio digitale";
        Size=new Size(1180,820);MinimumSize=new Size(800,600);StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(252,248,255);
        Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        browser.Dock=DockStyle.Fill;Controls.Add(browser);
        Shown+=async(s,e)=>{try{await StartApp();}catch(Exception error){MessageBox.Show(this,"Avvio di Coralì Lab interrotto: "+error.Message,"Coralì Lab");closing=true;Close();}};
        FormClosing+=OnClosing;
    }
    async Task StartApp(){
        data=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"CoraliLab");
        Directory.CreateDirectory(data);
        bridge=new TcpListener(IPAddress.Loopback,0);bridge.Start();
        int port=((IPEndPoint)bridge.LocalEndpoint).Port;
        var thread=new Thread(ServeBridge);thread.IsBackground=true;thread.Start();
        var info=new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"CoraliBackend.exe"));
        info.Arguments="--serve-only --data \""+data+"\"";
        info.UseShellExecute=false;info.CreateNoWindow=true;info.WorkingDirectory=AppDomain.CurrentDomain.BaseDirectory;
        info.EnvironmentVariables["CORALI_NATIVE_UI_URL"]="http://127.0.0.1:"+port;
        info.EnvironmentVariables["CORALI_NATIVE_UI_TOKEN"]=secret;
        backend=Process.Start(info);
        string url=null;
        for(int i=0;i<300;i++){
            if(backend.HasExited)throw new Exception("Il servizio locale si è fermato.");
            try{
                var session=Json().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(data,"session.json"),Encoding.UTF8));
                if(Convert.ToInt32(session["pid"])==backend.Id){url=(string)session["url"];break;}
            }catch(IOException){}catch(ArgumentException){}
            await Task.Delay(100);
        }
        if(url==null)throw new Exception("Il servizio locale non è pronto.");
        var parts=url.Split(new string[]{"/#"},StringSplitOptions.None);origin=parts[0];backendToken=parts[1];
        var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(data,"webview-arm64"));
        await browser.EnsureCoreWebView2Async(environment);
        browser.CoreWebView2.Settings.IsStatusBarEnabled=false;
        browser.CoreWebView2.NewWindowRequested+=(s,e)=>{e.Handled=true;};
        browser.CoreWebView2.PermissionRequested+=(s,e)=>{
            Uri uri;
            bool local=Uri.TryCreate(e.Uri,UriKind.Absolute,out uri)&&uri.GetLeftPart(UriPartial.Authority)==origin;
            e.State=local&&e.PermissionKind.ToString()=="Microphone"?CoreWebView2PermissionState.Allow:CoreWebView2PermissionState.Deny;
        };
        browser.Source=new Uri(url);
    }
    void ServeBridge(){
        while(!closing){
            TcpClient client;
            try{client=bridge.AcceptTcpClient();}catch{return;}
            ThreadPool.QueueUserWorkItem(s=>HandleBridge(client));
        }
    }
    void HandleBridge(TcpClient client){
        using(client){
            try{
                client.ReceiveTimeout=10000;client.SendTimeout=10000;
                var stream=client.GetStream();var reader=new StreamReader(stream,Encoding.UTF8,false,1024,true);
                string request=reader.ReadLine();var headers=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
                for(int i=0;i<40;i++){string line=reader.ReadLine();if(string.IsNullOrEmpty(line))break;int colon=line.IndexOf(':');if(colon>0)headers[line.Substring(0,colon)]=line.Substring(colon+1).Trim();}
                string supplied;
                if(request==null||!request.StartsWith("POST ")||!headers.TryGetValue("X-Corali-Token",out supplied)||!String.Equals(secret,supplied,StringComparison.Ordinal)){Respond(stream,403,new{error="Accesso non consentito"});return;}
                int length=0;if(headers.ContainsKey("Content-Length"))int.TryParse(headers["Content-Length"],out length);
                if(length<0||length>32768){Respond(stream,400,new{error="Richiesta non valida"});return;}
                char[] body=new char[length];int read=0;while(read<length){int n=reader.Read(body,read,length-read);if(n==0)throw new IOException();read+=n;}
                var payload=Json().Deserialize<Dictionary<string,object>>(new string(body));
                string path=request.Split(' ')[1];
                if(path=="/save"){
                    string name=payload.ContainsKey("name")?Path.GetFileName((string)payload["name"]):"documento";
                    string selected=(string)Invoke(new Func<string>(()=>{
                        using(var dialog=new SaveFileDialog()){
                            dialog.FileName=name;dialog.Title="Salva una copia";dialog.Filter="Tutti i file (*.*)|*.*";
                            dialog.InitialDirectory=Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
                            dialog.OverwritePrompt=true;
                            return dialog.ShowDialog(this)==DialogResult.OK?dialog.FileName:null;
                        }
                    }));
                    Respond(stream,200,new{path=selected});return;
                }
                if(path=="/close"){Respond(stream,200,new{ok=true});BeginInvoke(new Action(()=>Close()));return;}
                Respond(stream,404,new{error="Operazione non disponibile"});
            }catch(Exception){try{Respond(client.GetStream(),500,new{error="La finestra di salvataggio non è disponibile"});}catch{}}
        }
    }
    void Respond(Stream stream,int status,object data){
        byte[] body=Encoding.UTF8.GetBytes(Json().Serialize(data));
        byte[] header=Encoding.ASCII.GetBytes("HTTP/1.1 "+status+" Result\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: "+body.Length+"\r\nConnection: close\r\n\r\n");
        stream.Write(header,0,header.Length);stream.Write(body,0,body.Length);stream.Flush();
    }
    void OnClosing(object sender,FormClosingEventArgs e){
        if(!closing&&MessageBox.Show(this,"Vuoi chiudere Coralì Lab? Eventuali modifiche non salvate andranno perse.","Coralì Lab",MessageBoxButtons.OKCancel,MessageBoxIcon.Question)!=DialogResult.OK){e.Cancel=true;return;}
        closing=true;if(bridge!=null)bridge.Stop();
        if(backend!=null&&!backend.HasExited){
            try{
                var request=(HttpWebRequest)WebRequest.Create(origin+"/rpc");request.Method="POST";request.ContentType="application/json";request.Headers["X-Corali-Token"]=backendToken;request.Timeout=2500;
                byte[] body=Encoding.UTF8.GetBytes("{\"cmd\":\"cancel\"}");request.ContentLength=body.Length;using(var stream=request.GetRequestStream())stream.Write(body,0,body.Length);using(var response=request.GetResponse()){}
            }catch{}
            try{var info=new ProcessStartInfo("taskkill.exe","/PID "+backend.Id+" /T /F");info.UseShellExecute=false;info.CreateNoWindow=true;using(var kill=Process.Start(info))kill.WaitForExit(3000);}catch{}
        }
    }
    [STAThread] static void Main(){CoreWebView2Environment.SetLoaderDllFolderPath(AppDomain.CurrentDomain.BaseDirectory);Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new NativeHost());}
}
