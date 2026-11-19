import SwiftUI
import UniformTypeIdentifiers

@main
struct PDFHubMac: App {
    @State private var paths: [URL] = []
    @State private var category: Int? = nil
    @State private var selected: String? = nil
    @State private var result: URL? = nil
    @State private var message = ""
    @State private var busy = false
    private let groups = [
        ("Organizza", "square.grid.3x3.fill", ["merge","split","extract","remove","order","rotate","scan"]),
        ("Converti in PDF", "doc.badge.plus", ["fromimg","wordin","excelin","pptin","html","txtin"]),
        ("Esporta", "square.and.arrow.up", ["toimg","wordout","excelout","pptout","text","markdown","images"]),
        ("Ottimizza", "sparkles", ["compress","repair","ocr","pdfa"]),
        ("Modifica", "pencil.tip.crop.circle", ["numbers","watermark","crop","edit","sign","forms","newfield"]),
        ("Proteggi", "lock.shield", ["protect","unlock","redact","compare"]),
        ("Lingua e sintesi", "character.book.closed", ["summary","translate"])
    ]
    private let names = ["merge":"Unisci PDF","split":"Dividi PDF","extract":"Estrai pagine","remove":"Elimina pagine","order":"Riordina pagine","rotate":"Ruota PDF","scan":"Scansiona","fromimg":"Immagini in PDF","wordin":"Word in PDF","excelin":"Excel in PDF","pptin":"PowerPoint in PDF","html":"HTML in PDF","txtin":"Testo in PDF","toimg":"PDF in immagini","wordout":"PDF in Word","excelout":"PDF in Excel","pptout":"PDF in PowerPoint","text":"Estrai testo","markdown":"PDF in Markdown","images":"Estrai immagini","compress":"Comprimi PDF","repair":"Ripara PDF","ocr":"Riconosci testo","pdfa":"PDF/A-2b","numbers":"Numera pagine","watermark":"Filigrana","crop":"Ritaglia","edit":"Aggiungi testo","sign":"Apponi firma","forms":"Compila modulo","newfield":"Crea campo","protect":"Proteggi PDF","unlock":"Sblocca PDF","redact":"Oscura testo","compare":"Confronta PDF","summary":"Riassumi","translate":"Traduci PDF"]
    var body: some Scene {
        WindowGroup("PDFHub") {
            ZStack {
                Color(red:0.055, green:0.105, blue:0.09).ignoresSafeArea()
                VStack(spacing:18) {
                    Image(nsImage:NSImage(named:NSImage.applicationIconName) ?? NSImage()).resizable().frame(width:64,height:64)
                    Text("PDFHub").font(.system(size:29,weight:.bold,design:.rounded)).foregroundStyle(.white)
                    Text(paths.map(\.lastPathComponent).joined(separator:" · ")).font(.caption).foregroundStyle(.white.opacity(0.72)).lineLimit(1)
                    if selected == nil {
                        if let category {
                            Text(groups[category].0).font(.headline).foregroundStyle(.white)
                            LazyVGrid(columns:[GridItem(.flexible()),GridItem(.flexible())],spacing:9) {
                                ForEach(groups[category].2,id:\.self) { tool in
                                    Button(names[tool] ?? tool) { selected=tool }.buttonStyle(.bordered).tint(.orange)
                                }
                            }
                            Button("‹  Categorie") { self.category=nil }.foregroundStyle(.orange)
                        } else {
                            ZStack {
                                Circle().stroke(.white.opacity(0.16),lineWidth:1).frame(width:282,height:282)
                                Circle().stroke(.white.opacity(0.12),lineWidth:1).frame(width:194,height:194)
                                ForEach(groups.indices,id:\.self) { index in
                                    let angle=Double(index)*2*Double.pi/Double(groups.count)-Double.pi/2
                                    Button { category=index } label: {
                                        VStack(spacing:6) {
                                            Image(systemName:groups[index].1).font(.title3).foregroundStyle(Color.orange)
                                            Text(groups[index].0).font(.system(size:10,weight:.semibold)).multilineTextAlignment(.center).foregroundStyle(.white)
                                        }.frame(width:94,height:70).background(.white.opacity(0.065),in:RoundedRectangle(cornerRadius:19)).overlay(RoundedRectangle(cornerRadius:19).stroke(.orange.opacity(0.45),lineWidth:1))
                                    }.buttonStyle(.plain).offset(x:106*cos(angle),y:106*sin(angle))
                                }
                                Circle().fill(Color(red:0.11,green:0.17,blue:0.145)).frame(width:102,height:102)
                                Image(systemName:"doc.text.image").font(.system(size:40)).foregroundStyle(.orange).allowsHitTesting(false)
                            }.frame(width:320,height:320)
                            Text("Trascina un file sulla ruota oppure scegli una categoria").font(.caption).foregroundStyle(.white.opacity(0.68))
                            HStack {
                                Button("Scegli file…") { chooseFiles() }.buttonStyle(.borderedProminent).tint(.orange)
                                Button("Aggiungi alla scrivania") { installIcon() }.buttonStyle(.bordered).tint(.white)
                            }
                        }
                    } else {
                        Text(names[selected!] ?? selected!).font(.title2.bold()).foregroundStyle(.white)
                        Text(paths.isEmpty ? "Seleziona un file per continuare." : "Converti localmente i tuoi documenti").foregroundStyle(.white.opacity(0.72))
                        HStack {
                            Button("Aggiungi file…") { chooseFiles() }.buttonStyle(.bordered).tint(.white)
                            Button("Indietro") { selected=nil }.buttonStyle(.bordered).tint(.white)
                            Button("Esegui e salva") { convert() }.buttonStyle(.borderedProminent).tint(.orange).disabled(paths.isEmpty || busy)
                        }
                    }
                    if busy { ProgressView().tint(.orange) }
                    if !message.isEmpty { Text(message).font(.caption).foregroundStyle(.orange) }
                    if let result {
                        ShareLink(item:result){ Label("Apri risultato · \(result.lastPathComponent)",systemImage:"arrow.down.doc.fill") }.tint(.orange)
                    }
                    Text("I file restano sul tuo Mac").font(.system(size:10,design:.monospaced)).foregroundStyle(.white.opacity(0.55))
                }.padding(25).frame(width:530)
            }
            .onOpenURL { url in paths=[url];selected=nil;category=nil;message="" }
            .onDrop(of:[UTType.fileURL],isTargeted:nil) { items in
                for item in items { _ = item.loadObject(ofClass:URL.self) { url,_ in if let url { DispatchQueue.main.async { paths.append(url) } } } }
                return true
            }
        }.windowResizability(.contentSize)
    }
    private func chooseFiles() {
        let panel=NSOpenPanel();panel.allowsMultipleSelection=true;panel.canChooseDirectories=false
        if panel.runModal() == NSApplication.ModalResponse.OK { paths += panel.urls }
    }
    private func convert() {
        guard let selected else {return}
        let panel=NSSavePanel();panel.nameFieldStringValue=(paths.first?.deletingPathExtension().lastPathComponent ?? "documento")+"-pdfhub.pdf"
        guard panel.runModal() == NSApplication.ModalResponse.OK,let output=panel.url else{return}
        busy=true;message=""
        DispatchQueue.global(qos:.userInitiated).async {
            var options:[String:String]=[:]
            if selected=="merge" || selected=="fromimg" { options=["mode":"all"] }
            if selected=="split" { options=["mode":"all"] }
            if selected=="rotate" { options=["angle":"90"] }
            if selected=="compress" { options=["level":"strong"] }
            if selected=="toimg" { options=["format":"jpg"] }
            if selected=="protect" { options=["password":""]; }
            if selected=="unlock" { options=["source_password":""]; }
            var job:[String:Any]=["op":selected,"files":paths.map(\.path),"options":options,"output":output.path]
            let pipe=Process();pipe.executableURL=Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/engine/engine")
            let stdin=Pipe(),stdout=Pipe();pipe.standardInput=stdin;pipe.standardOutput=stdout
            do {
                try pipe.run();let data=try JSONSerialization.data(withJSONObject:job);stdin.fileHandleForWriting.write(data);try stdin.fileHandleForWriting.close()
                let response=stdout.fileHandleForReading.readDataToEndOfFile();pipe.waitUntilExit()
                let record=try JSONSerialization.jsonObject(with:response) as? [String:String] ?? [:]
                if pipe.terminationStatus != 0 || record["error"] != nil { throw NSError(domain:"PDFHub",code:1,userInfo:[NSLocalizedDescriptionKey:record["error"] ?? "Conversione non riuscita."]) }
                DispatchQueue.main.async { self.busy=false;self.result=output;self.message="Conversione completata." }
            } catch {DispatchQueue.main.async {self.busy=false;self.message=error.localizedDescription}}
        }
    }
    private func installIcon() {
        let destination=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Desktop/PDFHub.app")
        do { try? FileManager.default.removeItem(at:destination);try FileManager.default.copyItem(at:Bundle.main.bundleURL,to:destination);NSWorkspace.shared.activateFileViewerSelecting([destination]) }
        catch {message=error.localizedDescription}
    }
}
