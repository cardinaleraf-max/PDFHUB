using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

public class Scenario {public string label,op,target; public string[] files; public Dictionary<string,string> options;}
internal static class NativeChecks
{
    static T Field<T>(object obj,string key){return (T)obj.GetType().GetField(key,BindingFlags.NonPublic|BindingFlags.Instance).GetValue(obj);}
    static void Check(bool condition,string info){if(!condition)throw new Exception(info);}
    static void CheckTargets(Canvas canvas){
        var buttons=canvas.Children.OfType<Button>().ToArray();
        for(int i=0;i<buttons.Length;i++){
            double angle=(-90+i*360.0/Math.Max(2,buttons.Length))*Math.PI/180;
            DependencyObject hit=canvas.InputHitTest(new Point(240+165*Math.Cos(angle),240+165*Math.Sin(angle))) as DependencyObject;
            while(hit!=null&&!(hit is Button))hit=VisualTreeHelper.GetParent(hit);
            Check(hit==buttons[i],"Area cliccabile: "+AutomationProperties.GetName(buttons[i]));
        }
    }
    [STAThread] static int Main(string[] args){
        var app=new Application{ShutdownMode=ShutdownMode.OnExplicitShutdown};
        int result=1;
        app.Startup+=async(s,e)=>{
            try{
                var directory=Path.GetDirectoryName(args[0]);
                var shortcut=Launcher.CreateShortcut(directory);
                Check(File.Exists(shortcut)&&Launcher.CreateShortcut(directory)==shortcut,"Installazione collegamento");
                var json=new JavaScriptSerializer();
                var catalog=json.Deserialize<Catalog>(File.ReadAllText(Path.Combine(Launcher.Root,"ui/catalog.json")));
                var cases=json.Deserialize<Scenario[]>(File.ReadAllText(args[0]));
                int tested=0;
                foreach(var sample in cases){
                    var tool=catalog.groups.SelectMany(g=>g.tools).Single(t=>t.id==sample.op);
                    if(sample.files.Length>0){
                        var orbit=new Orbit(catalog,sample.files);orbit.Show();orbit.UpdateLayout();
                        var canvas=Field<Canvas>(orbit,"canvas");
                        CheckTargets(canvas);
                        var group=catalog.groups.First(g=>g.tools.Any(t=>t.id==tool.id));
                        var sector=canvas.Children.OfType<Button>().Single(p=>AutomationProperties.GetName(p)==group.name);
                        sector.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                        orbit.UpdateLayout();CheckTargets(canvas);
                        Check(canvas.Children.OfType<Button>().Any(p=>AutomationProperties.GetName(p)==tool.title),sample.label+" orbita");
                        orbit.Close();
                    }
                    string dest=sample.target;
                    var editor=new QuickEditor(catalog,tool,sample.files,dlg=>{dlg.FileName=dest;return true;});
                    editor.Show();editor.UpdateLayout();
                    var form=Field<StackPanel>(editor,"form");
                    // Le etichette e i controlli sono creati dal catalogo condiviso.
                    foreach(var entry in sample.options){
                        var label=entry.Key=="source_password"?"Password di apertura (per PDF protetti)":catalog.fields[entry.Key][0];
                        int i=form.Children.Cast<UIElement>().ToList().FindIndex(c=>c is TextBlock && ((TextBlock)c).Text==label);
                        var control=form.Children[i+1];
                        if(control is ComboBox){
                            var choices=catalog.fields[entry.Key].Skip(3).ToArray();
                            ((ComboBox)control).SelectedIndex=Array.FindIndex(choices,c=>c.Split('|')[0]==entry.Value);
                        }else if(control is PasswordBox)((PasswordBox)control).Password=entry.Value;
                        else ((TextBox)control).Text=entry.Value;
                    }
                    Field<Button>(editor,"action").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                    for(int i=0;i<3300&&Field<bool>(editor,"busy");i++)await Task.Delay(100);
                    var status=Field<TextBlock>(editor,"status").Text;
                    Check(!Field<bool>(editor,"busy"),sample.label+" timeout");
                    if(!File.Exists(dest))File.WriteAllText(dest+".error",status);
                    if(editor.IsVisible)editor.Close();
                    Console.WriteLine(sample.label+" "+status);tested++;
                }
                Check(tested==cases.Length,"casi mancanti");result=0;
            }catch(Exception ex){Console.Error.WriteLine(ex);}
            finally{app.Shutdown();}
        };
        app.Run();return result;
    }
}
