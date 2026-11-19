using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Win32;

internal sealed class QuickEditor : Window
{
    readonly Tool tool;
    readonly ObservableCollection<string> files;
    readonly Dictionary<string,Func<string>> fields=new Dictionary<string,Func<string>>();
    readonly StackPanel form=new StackPanel(),layout=new StackPanel{Margin=new Thickness(24)};
    readonly ListBox list=new ListBox{MinHeight=40,MaxHeight=105};
    readonly Button action=new Button();
    readonly TextBlock status=new TextBlock{TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,10,0,6)};
    readonly ProgressBar progress=new ProgressBar{Height=3};
    bool busy;
    internal bool Saved {get;private set;}
    string folder,resultName;
    readonly Func<SaveFileDialog,bool> chooseDestination;
    public QuickEditor(Catalog catalog,Tool selected,string[] initial,Func<SaveFileDialog,bool> destination=null){
        chooseDestination=destination??(dialog=>dialog.ShowDialog(this)==true);
        tool=selected;files=new ObservableCollection<string>(initial);
        Title="PDFHub · "+tool.title;Width=450;SizeToContent=SizeToContent.Height;
        MaxHeight=SystemParameters.WorkArea.Height-20;WindowStartupLocation=WindowStartupLocation.CenterScreen;
        Background=new SolidColorBrush(Color.FromRgb(249,250,245));
        Content=new ScrollViewer{Content=layout,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        layout.Children.Add(new TextBlock{Text=tool.title,FontSize=24,FontWeight=FontWeights.SemiBold});
        Label(layout,tool.description);
        layout.Children.Add(form);list.ItemsSource=files;form.Children.Add(list);
        var buttons=new WrapPanel();form.Children.Add(buttons);
        if(tool.max==0){buttons.Visibility=Visibility.Collapsed;list.Visibility=Visibility.Collapsed;}
        ButtonFor(buttons,"Aggiungi",()=>{
            var pick=new OpenFileDialog{Multiselect=tool.max>1,Filter="File compatibili|"+string.Join(";",tool.accept.Split(',').Select(e=>"*"+e))};
            if(pick.ShowDialog(this)==true)foreach(var p in pick.FileNames)files.Add(p);
        });
        ButtonFor(buttons,"Rimuovi",()=>{if(list.SelectedIndex>=0)files.RemoveAt(list.SelectedIndex);});
        ButtonFor(buttons,"↑",()=>Move(-1));ButtonFor(buttons,"↓",()=>Move(1));
        var selects=new Dictionary<string,ComboBox>();
        foreach(string key in tool.fields){
            string[] def=catalog.fields[key];var caption=Label(form,def[0]);
            if(def[1]=="select"){
                var choices=def.Skip(3).Select(s=>s.Split('|')).ToArray();
                var control=new ComboBox{ItemsSource=choices.Select(c=>c[1]),SelectedIndex=Array.FindIndex(choices,c=>c[0]==def[2])};
                form.Children.Add(control);fields[key]=()=>choices[control.SelectedIndex][0];selects[key]=control;
            }else AddInput(key,def[2],def[1]=="password");
            string mode=key=="pages"&&tool.id=="split"?"mode":key=="model"&&tool.id=="summary"?"method":null;
            if(mode!=null){
                var input=form.Children[form.Children.Count-1];
                Action update=()=>{caption.Visibility=input.Visibility=selects[mode].SelectedIndex==1?Visibility.Visible:Visibility.Collapsed;};
                selects[mode].SelectionChanged+=(s,e)=>update();update();
            }
        }
        if(tool.accept==".pdf"){Label(form,"Password di apertura (per PDF protetti)");AddInput("source_password","",true);}
        layout.Children.Add(status);layout.Children.Add(progress);layout.Children.Add(action);
        action.Content="Esegui e salva";action.Padding=new Thickness(15,9,15,9);action.Margin=new Thickness(0,10,0,0);
        action.Background=new SolidColorBrush(Color.FromRgb(233,92,49));action.Foreground=Brushes.White;
        action.Click+=async (s,e)=>await Execute();
        Closing+=(s,e)=>{if(busy)e.Cancel=true;};
        Closed+=(s,e)=>Clean();
    }
    void Clean(){if(folder!=null){try{File.Delete(Path.Combine(folder,"result"));Directory.Delete(folder);}catch(IOException){}folder=null;}}
    static TextBlock Label(Panel parent,string text){
        var caption=new TextBlock{Text=text,TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,8,0,4)};
        parent.Children.Add(caption);return caption;
    }
    static void ButtonFor(Panel parent,string title,Action handler){
        var button=new Button{Content=title,Margin=new Thickness(0,5,4,0),Padding=new Thickness(8,3,8,3)};
        button.Click+=(s,e)=>handler();parent.Children.Add(button);
    }
    void Move(int offset){
        int index=list.SelectedIndex,end=index+offset;
        if(index>=0&&end>=0&&end<files.Count){files.Move(index,end);list.SelectedIndex=end;}
    }
    void AddInput(string name,string initial,bool secret){
        if(secret){var pw=new PasswordBox();form.Children.Add(pw);fields[name]=()=>pw.Password;}
        else{var input=new TextBox{Text=initial};form.Children.Add(input);fields[name]=()=>input.Text;}
    }
    string Work(string job){
        var start=new ProcessStartInfo(Launcher.Python("python.exe"),"-X utf8 -B \""+Path.Combine(Launcher.Root,"worker.py")+"\""){
            CreateNoWindow=true,UseShellExecute=false,WorkingDirectory=Launcher.Root,
            RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,
            StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
        using(var process=Process.Start(start)){
            byte[] data=Encoding.UTF8.GetBytes(job);
            process.StandardInput.BaseStream.Write(data,0,data.Length);process.StandardInput.Close();
            var errors=process.StandardError.ReadToEndAsync();
            string response=process.StandardOutput.ReadToEnd();process.WaitForExit();
            if(process.ExitCode!=0)throw new IOException("Errore del motore PDF. "+errors.Result);
            var record=new JavaScriptSerializer().Deserialize<Dictionary<string,string>>(response);
            if(record.ContainsKey("error"))throw new IOException(record["error"]);
            return record["name"];
        }
    }
    async Task Execute(){
        if(busy)return;
        try{
            if(resultName==null){
                if(files.Count<tool.min||files.Count>tool.max)throw new IOException("Numero di file richiesto: "+tool.min+"–"+tool.max+".");
                Clean();folder=Path.Combine(Path.GetTempPath(),"pdfhub-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
                var job=new JavaScriptSerializer().Serialize(new{op=tool.id,files=files.ToArray(),options=fields.ToDictionary(v=>v.Key,v=>v.Value()),output=Path.Combine(folder,"result")});
                busy=true;form.IsEnabled=false;action.IsEnabled=false;progress.IsIndeterminate=true;status.Text="Elaborazione sul dispositivo…";
                resultName=await Task.Run(()=>Work(job));
                status.Text="Conversione completata.";action.Content="Salva risultato";
            }
            string extension=Path.GetExtension(resultName);
            var save=new SaveFileDialog{FileName=resultName,DefaultExt=extension,Filter=extension.Substring(1).ToUpperInvariant()+"|*"+extension,
                InitialDirectory=files.Count==0?"":Path.GetDirectoryName(files[0])};
            if(chooseDestination(save)){
                string temp=Path.Combine(Path.GetDirectoryName(save.FileName),".pdfhub-"+Guid.NewGuid().ToString("N")+".tmp");
                try{File.Copy(Path.Combine(folder,"result"),temp);
                    if(File.Exists(save.FileName))File.Replace(temp,save.FileName,null);else File.Move(temp,save.FileName);
                }finally{if(File.Exists(temp))File.Delete(temp);}
                busy=false;Saved=true;Close();
            }
        }catch(Exception error){status.Text=error.Message;}
        finally{busy=false;progress.IsIndeterminate=false;action.IsEnabled=true;form.IsEnabled=resultName==null;}
    }
}
