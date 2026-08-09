import UIKit
import Social
import UniformTypeIdentifiers

// SignalLoop Share surface (plan.md §4; AGENTS.md multi-surface parity).
//
// A share extension runs in its OWN process, so it cannot link the in-app
// LoopCommandBus object. Instead it speaks the SAME command-bus protocol over
// HTTP: POST /v1/commands { type: "log_evidence", source: "share",
// idempotency_key }. The invariant still holds — every surface funnels through
// the command bus into the LoopEngine; here the hop is HTTP, not in-process.
//
// Safety: this surface ONLY logs evidence (safe, reversible). It never
// externalizes — sending or posting stays an authenticated in-app review.
//
// Dev note: base URL / API key are read from UserDefaults.standard with a dev
// fallback. A production build should share these via an App Group suite so the
// extension honors the user's in-app settings across the process boundary.

struct ShareLoop {
    let id: String
    let title: String
    let domain: String
    let status: String
}

final class ShareViewController: SLComposeServiceViewController {
    private var baseURL = URL(string: "http://127.0.0.1:8787")!
    private var apiKey = "dev-key-change-me"
    private var loops: [ShareLoop] = []
    private var selected: ShareLoop?
    private var sharedURL: String?

    override func viewDidLoad() {
        super.viewDidLoad()
        loadSettings()
        title = "SignalLoop"
        placeholder = "Log this to a loop…"
        extractSharedItem()
        fetchLoops()
    }

    private func loadSettings() {
        guard let data = UserDefaults.standard.data(forKey: "chitti.client.settings"),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }
        if let b = obj["baseURL"] as? String, let u = URL(string: b) { baseURL = u }
        if let k = obj["apiKey"] as? String, !k.isEmpty { apiKey = k }
    }

    private func authorize(_ req: inout URLRequest) {
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    }

    // Pull shared text / URL / image into the compose box.
    private func extractSharedItem() {
        guard let item = extensionContext?.inputItems.first as? NSExtensionItem,
              let providers = item.attachments else { return }
        let urlType = UTType.url.identifier
        let textType = UTType.plainText.identifier
        let imageType = UTType.image.identifier
        for p in providers {
            if p.hasItemConformingToTypeIdentifier(urlType) {
                p.loadItem(forTypeIdentifier: urlType, options: nil) { [weak self] v, _ in
                    guard let u = v as? URL else { return }
                    DispatchQueue.main.async {
                        self?.sharedURL = u.absoluteString
                        self?.appendToText(u.absoluteString)
                    }
                }
            } else if p.hasItemConformingToTypeIdentifier(imageType) {
                DispatchQueue.main.async { self.appendToText("[photo]") }
            } else if p.hasItemConformingToTypeIdentifier(textType) {
                p.loadItem(forTypeIdentifier: textType, options: nil) { [weak self] v, _ in
                    guard let t = v as? String else { return }
                    DispatchQueue.main.async { self?.appendToText(t) }
                }
            }
        }
    }

    private func appendToText(_ s: String) {
        let cur = contentText ?? ""
        textView.text = cur.isEmpty ? s : cur + "\n" + s
        validateContent()
    }

    private func fetchLoops() {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/loops"))
        authorize(&req)
        URLSession.shared.dataTask(with: req) { [weak self] data, _, _ in
            guard let self, let data,
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let arr = obj["loops"] as? [[String: Any]] else { return }
            let parsed = arr.compactMap { d -> ShareLoop? in
                guard let id = d["id"] as? String, let t = d["title"] as? String else { return nil }
                return ShareLoop(id: id, title: t,
                                 domain: d["domain"] as? String ?? "",
                                 status: d["status"] as? String ?? "")
            }
            DispatchQueue.main.async {
                self.loops = parsed
                self.selected = parsed.first(where: { $0.status != "done" }) ?? parsed.first
                self.reloadConfigurationItems()
                self.validateContent()
            }
        }.resume()
    }

    override func isContentValid() -> Bool {
        selected != nil && !(contentText ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    override func didSelectPost() {
        guard let loop = selected else {
            extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
            return
        }
        var payload: [String: Any] = ["loop_id": loop.id, "kind": "note"]
        let text = (contentText ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if let u = sharedURL { payload["url"] = u; payload["kind"] = "link" }
        if !text.isEmpty { payload["text"] = text }

        let body: [String: Any] = [
            "type": "log_evidence",
            "payload": payload,
            "source": "share",
            "idempotency_key": UUID().uuidString,
        ]
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/commands"))
        req.httpMethod = "POST"
        authorize(&req)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: req) { [weak self] _, _, _ in
            self?.extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
        }.resume()
    }

    override func configurationItems() -> [Any]! {
        guard let item = SLComposeSheetConfigurationItem() else { return [] }
        item.title = "Loop"
        item.value = selected?.title ?? (loops.isEmpty ? "No loops" : "Choose…")
        item.tapHandler = { [weak self] in
            guard let self else { return }
            let picker = LoopPickerController(loops: self.loops) { chosen in
                self.selected = chosen
                self.reloadConfigurationItems()
                self.validateContent()
            }
            self.pushConfigurationViewController(picker)
        }
        return [item]
    }
}

/// Simple loop chooser pushed from the share sheet's configuration row.
final class LoopPickerController: UITableViewController {
    private let loops: [ShareLoop]
    private let onPick: (ShareLoop) -> Void

    init(loops: [ShareLoop], onPick: @escaping (ShareLoop) -> Void) {
        self.loops = loops
        self.onPick = onPick
        super.init(style: .plain)
        title = "Choose loop"
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        loops.count
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .subtitle, reuseIdentifier: nil)
        let loop = loops[indexPath.row]
        cell.textLabel?.text = loop.title
        cell.detailTextLabel?.text = "\(loop.domain) · \(loop.status)"
        return cell
    }

    override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        onPick(loops[indexPath.row])
        navigationController?.popViewController(animated: true)
    }
}
