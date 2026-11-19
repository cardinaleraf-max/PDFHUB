using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using Forms = System.Windows.Forms;
using FilePath = System.IO.Path;

public class Tool { public string id, title, description, accept; public int min, max; public string[] fields; }
public class Group { public string name, glyph, color; public Tool[] tools; }
public class Catalog { public Group[] groups; public Dictionary<string,string[]> fields; }

internal static class Launcher
{
    internal static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
    internal static string Python(string name){
        string portable=FilePath.Combine(Root,"runtime",name);
        return File.Exists(portable)?portable:name;
    }
    internal static string CreateShortcut(string directory)
    {
        string target=FilePath.Combine(Root,"PDFHub.exe");
        string name=FilePath.Combine(directory,"PDFHub Desktop.lnk");
        dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        dynamic link=shell.CreateShortcut(name);
        try {
            if(File.Exists(name)&&!String.Equals((string)link.TargetPath,target,StringComparison.OrdinalIgnoreCase))
                throw new IOException("Esiste già un collegamento PDFHub con una destinazione diversa.");
            link.TargetPath=target;link.WorkingDirectory=Root;link.IconLocation=target+",0";
            link.Description="Apri PDFHub o trascina qui i file per scegliere uno strumento.";
            link.Save();
            return name;
        }finally{Marshal.FinalReleaseComObject(link);Marshal.FinalReleaseComObject(shell);}
    }
    internal static void Run(string script, IEnumerable<string> args)
    {
        // Windows paths and operation identifiers cannot contain double quotes.
        string arguments = string.Join(" ", new[]{FilePath.Combine(Root,script)}.Concat(args).Select(s => "\"" + s + "\""));
        Process.Start(new ProcessStartInfo(Python("pythonw.exe"),arguments) {
            WorkingDirectory=Root, UseShellExecute=false, CreateNoWindow=true
        });
    }
    [STAThread] private static void Main(string[] args)
    {
        try {
            if(args.Length==1 && args[0]=="--desktop-shortcut"){
                var shortcut=CreateShortcut(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory));
                MessageBox.Show("Collegamento pronto. Trascina un file sull’icona PDFHub Desktop.\n\n"+shortcut,"PDFHub");
                return;
            }
            if (args.Length==0) { Run("PDFHub.pyw",new string[0]); return; }
            bool manual=args.Length==1&&args[0]=="--manual";
            if(manual)args=new string[0];
            if (args.Any(p=>!File.Exists(p))) throw new InvalidOperationException("Trascina file esistenti sull’icona PDFHub.");
            var json=File.ReadAllText(FilePath.Combine(Root,"ui","catalog.json"));
            var catalog=new JavaScriptSerializer().Deserialize<Catalog>(json);
            new Application().Run(new Orbit(catalog,args.Select(FilePath.GetFullPath).ToArray()));
        } catch(Exception error) { MessageBox.Show(error.Message,"PDFHub",MessageBoxButton.OK,MessageBoxImage.Information); }
    }
}

internal class Orbit : Window
{
    const double Center=240;
    readonly Canvas canvas=new Canvas { Width=480, Height=480 };
    readonly Catalog catalog;
    string[] files;
    Group current;
    static SolidColorBrush Brush(string color) { return new SolidColorBrush((Color)ColorConverter.ConvertFromString(color)); }
    static Point Polar(double r,double angle) {
        double a=angle*Math.PI/180;
        return new Point(Center+r*Math.Cos(a),Center+r*Math.Sin(a));
    }
    public Orbit(Catalog data,string[] paths) {
        catalog=data; files=paths;
        Title="PDFHub · Orbita"; WindowStyle=WindowStyle.None; AllowsTransparency=true;
        Background=Brushes.Transparent; ResizeMode=ResizeMode.NoResize; Topmost=true;
        ShowInTaskbar=false; Width=480; Height=480; AllowDrop=true;
        Content=new Viewbox {Child=canvas};
        var images=BitmapDecoder.Create(new Uri(FilePath.Combine(Launcher.Root,"ui","icon.ico")),
            BitmapCreateOptions.PreservePixelFormat,BitmapCacheOption.OnLoad);
        Icon=images.Frames.OrderByDescending(frame=>frame.PixelWidth).First();
        Loaded+=(s,e)=>{
            var mouse=Forms.Cursor.Position;
            var area=Forms.Screen.FromPoint(mouse).WorkingArea;
            var transform=PresentationSource.FromVisual(this).CompositionTarget.TransformFromDevice;
            var min=transform.Transform(new Point(area.Left,area.Top));
            var max=transform.Transform(new Point(area.Right,area.Bottom));
            var p=transform.Transform(new Point(mouse.X,mouse.Y));
            Width=Height=Math.Min(480,Math.Min(max.X-min.X,max.Y-min.Y));
            Left=Math.Max(min.X,Math.Min(max.X-Width,p.X-Width/2));
            Top=Math.Max(min.Y,Math.Min(max.Y-Height,p.Y-Height/2));
            Draw(null); Activate(); Focus();
        };
        KeyDown+=(s,e)=>{if(e.Key==Key.Escape) { if(current==null) Close(); else Draw(null); e.Handled=true; }};
        Drop+=(s,e)=>{
            var incoming=e.Data.GetData(DataFormats.FileDrop) as string[];
            if(incoming!=null && incoming.All(File.Exists)){files=incoming; Draw(null);}
        };
    }
    static TextBlock Text(string label,double size,string color) {
        return new TextBlock{Text=label,FontFamily=new FontFamily("Segoe UI"),FontSize=size,
            Foreground=Brush(color),TextAlignment=TextAlignment.Center,TextWrapping=TextWrapping.Wrap,
            VerticalAlignment=VerticalAlignment.Center,HorizontalAlignment=HorizontalAlignment.Center};
    }
    void Place(UIElement control,double x,double y) { Canvas.SetLeft(control,x);Canvas.SetTop(control,y);canvas.Children.Add(control); }
    static void Action(UIElement element,string name,Action run) {
        element.Focusable=true; AutomationProperties.SetName(element,name);
        element.MouseLeftButtonUp+=(s,e)=>{e.Handled=true;run();};
        element.KeyDown+=(s,e)=>{if(e.Key==Key.Enter||e.Key==Key.Space){e.Handled=true;run();}};
        element.GotKeyboardFocus+=(s,e)=>element.Opacity=.8;
        element.LostKeyboardFocus+=(s,e)=>element.Opacity=1;
    }
    void Sector(double angle,double step,string title,string glyph,string color,Action choose,string hint) {
        double start=angle-step/2+1, end=angle+step/2-1;
        var shape=new StreamGeometry();
        using(var g=shape.Open()){
            g.BeginFigure(Polar(225,start),true,true);
            g.ArcTo(Polar(225,end),new Size(225,225),0,end-start>180,SweepDirection.Clockwise,true,false);
            g.LineTo(Polar(106,end),true,false);
            g.ArcTo(Polar(106,start),new Size(106,106),0,end-start>180,SweepDirection.Counterclockwise,true,false);
        }
        shape.Freeze();
        var rest=new LinearGradientBrush(Color.FromRgb(52,68,59),Color.FromRgb(27,39,34),55);
        var face=new System.Windows.Shapes.Path {Data=shape,Fill=rest,Stroke=Brush(color),StrokeThickness=1};
        var sector=new Button {Content=face,Width=480,Height=480,Clip=shape,Cursor=Cursors.Hand,ToolTip=hint,
            Template=new ControlTemplate(typeof(Button)){VisualTree=new FrameworkElementFactory(typeof(ContentPresenter))}};
        Place(sector,0,0);
        sector.MouseEnter+=(s,e)=>{face.Fill=Brush("#FF39463F");face.StrokeThickness=2.6;};
        sector.MouseLeave+=(s,e)=>{face.Fill=rest;face.StrokeThickness=1;};
        sector.GotKeyboardFocus+=(s,e)=>face.Fill=Brush("#FF455348");
        sector.LostKeyboardFocus+=(s,e)=>face.Fill=rest;
        AutomationProperties.SetName(sector,title);
        sector.Click+=(s,e)=>choose();
        var point=Polar(165,angle);
        var stack=new StackPanel {Width=100,IsHitTestVisible=false};
        var mark=Text(char.ConvertFromUtf32(Convert.ToInt32(glyph,16)),22,color);
        mark.FontFamily=new FontFamily("Segoe MDL2 Assets");stack.Children.Add(mark);
        var caption=Text(title,13,"#FFF6F5EC");caption.Margin=new Thickness(0,5,0,0);caption.FontWeight=FontWeights.SemiBold;
        stack.Children.Add(caption);stack.Measure(new Size(100,100));
        Place(stack,point.X-50,point.Y-stack.DesiredSize.Height/2);
    }
    bool Fits(Tool tool) {
        string[] extensions=tool.accept.Split(',');
        return files.Length<=tool.max && files.All(p=>extensions.Contains(FilePath.GetExtension(p),StringComparer.OrdinalIgnoreCase));
    }
    void PickFiles(){
        var picker=new Microsoft.Win32.OpenFileDialog{Multiselect=true,Title="Scegli i file per PDFHub"};
        if(picker.ShowDialog(this)==true){files=picker.FileNames;Draw(null);}
    }
    void Draw(Group group) {
        current=group;canvas.Children.Clear();
        var groups=catalog.groups.Where(g=>g.tools.Any(Fits)).ToArray();
        var items=group==null?null:group.tools.Where(Fits).ToArray();
        int count=group==null?groups.Length:items.Length;
        double step=360.0/Math.Max(2,count);
        for(int i=0;i<count;i++){
            if(group==null){
                var g=groups[i];Sector(-90+i*step,step,g.name,g.glyph,g.color,()=>Draw(g),g.name);
            }else{
                var t=items[i];Sector(-90+i*step,step,t.title,group.glyph,group.color,()=>{
                    try{
                        Hide();
                        var editor=new QuickEditor(catalog,t,files);
                        editor.ShowDialog();
                        if(editor.Saved)Close();else{Show();Activate();}
                    }
                    catch(Exception ex){MessageBox.Show(ex.Message,"PDFHub");}
                },t.description);
            }
        }
        if(count==1){
            if(group==null)Sector(90,180,"Scegli altri file","E8E5","#90A79A",PickFiles,"Cambia la selezione");
            else Sector(90,180,"Categorie","E72B","#90A79A",()=>Draw(null),"Torna alle categorie");
        }
        var hub=new Border {Width=192,Height=192,CornerRadius=new CornerRadius(96),Background=Brush("#FF202C27"),
            BorderBrush=Brush("#FF58665A"),BorderThickness=new Thickness(1.5),Cursor=Cursors.Hand};
        var content=new StackPanel{VerticalAlignment=VerticalAlignment.Center,Width=150};
        var logo=new Image{Width=52,Height=52,Source=Icon};
        RenderOptions.SetBitmapScalingMode(logo,BitmapScalingMode.HighQuality);content.Children.Add(logo);
        var title=Text(group==null?"PDFHub":group.name,19,"#FFFFF5E8");title.FontWeight=FontWeights.Bold;content.Children.Add(title);
        var file=Text(files.Length==0?"Scegli uno strumento":files.Length==1?FilePath.GetFileName(files[0]):files.Length+" file selezionati",11,"#FFC4CEC6");
        file.TextTrimming=TextTrimming.CharacterEllipsis;file.TextWrapping=TextWrapping.NoWrap;file.MaxWidth=136;file.ToolTip=string.Join("\n",files);content.Children.Add(file);
        var back=Text(count==0?"Formato non supportato · Chiudi":group!=null?"‹  Indietro":files.Length==0?"＋  Scegli file":"×  Chiudi",11,"#FFFFAF81");
        back.Margin=new Thickness(0,7,0,0);content.Children.Add(back);hub.Child=content;Place(hub,144,144);
        Action(hub,group!=null?"Indietro":files.Length==0?"Scegli file":"Chiudi",()=>{
            if(group!=null){Draw(null);return;}
            if(files.Length!=0){Close();return;}
            PickFiles();
        });
        if(SystemParameters.ClientAreaAnimation){
            canvas.BeginAnimation(OpacityProperty,new DoubleAnimation(.1,1,TimeSpan.FromMilliseconds(150)));
            var scale=new ScaleTransform(1,1,Center,Center);canvas.RenderTransform=scale;
            var animation=new DoubleAnimation(.94,1,TimeSpan.FromMilliseconds(180)){DecelerationRatio=.8};
            scale.BeginAnimation(ScaleTransform.ScaleXProperty,animation);scale.BeginAnimation(ScaleTransform.ScaleYProperty,animation);
        }
    }
}
