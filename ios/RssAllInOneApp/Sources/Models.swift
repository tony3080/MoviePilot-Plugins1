import Foundation

struct ServerConfig: Codable, Equatable, Sendable {
    var baseURL = ""
    var token = ""
    var instanceName = "家里 NAS"
}

// Preserve unknown server fields when editing complete configurations.
enum JSONValue: Codable, Equatable, Sendable {
    case object([String: JSONValue]), array([JSONValue]), string(String)
    case number(Double), bool(Bool), null

    init(from decoder: Decoder) throws {
        let box = try decoder.singleValueContainer()
        if box.decodeNil() { self = .null }
        else if let value = try? box.decode(Bool.self) { self = .bool(value) }
        else if let value = try? box.decode(Double.self) { self = .number(value) }
        else if let value = try? box.decode(String.self) { self = .string(value) }
        else if let value = try? box.decode([JSONValue].self) { self = .array(value) }
        else { self = .object(try box.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.singleValueContainer()
        switch self {
        case .object(let value): try box.encode(value)
        case .array(let value): try box.encode(value)
        case .string(let value): try box.encode(value)
        case .number(let value): try box.encode(value)
        case .bool(let value): try box.encode(value)
        case .null: try box.encodeNil()
        }
    }

    subscript(_ key: String) -> JSONValue {
        get { object[key] ?? .null }
        set { var copy = object; copy[key] = newValue; self = .object(copy) }
    }
    var object: [String: JSONValue] { if case .object(let value) = self { return value }; return [:] }
    var array: [JSONValue] { if case .array(let value) = self { return value }; return [] }
    var text: String {
        switch self {
        case .string(let value): return value
        case .number(let value): return value == value.rounded() ? String(format: "%.0f", value) : String(value)
        case .bool(let value): return value ? "开启" : "关闭"
        default: return ""
        }
    }
    var double: Double { if case .number(let value) = self { return value }; return Double(text) ?? 0 }
    var int: Int { Int(double) }
    var flag: Bool {
        switch self {
        case .bool(let value): return value
        case .number(let value): return value != 0
        case .string(let value): return ["true", "1"].contains(value.lowercased())
        default: return false
        }
    }
    static func strings(_ values: [String]) -> JSONValue { .array(values.map(JSONValue.string)) }
}

struct Record: Identifiable, Equatable, Sendable {
    var value: JSONValue
    var id: String {
        if !value["row_key"].text.isEmpty { return value["row_key"].text }
        if !value["id"].text.isEmpty { return value["id"].text }
        if !value["info_hash"].text.isEmpty { return value["downloader_id"].text + ":" + value["info_hash"].text }
        return [value["name"].text, value["domain"].text, value["path"].text, value["source_key"].text]
            .joined(separator: "|")
    }
    subscript(_ key: String) -> JSONValue { value[key] }
    var details: JSONValue { value["details"] }
    var title: String {
        [value["media_title"].text, value["title"].text, value["name"].text,
         value["source_name"].text].first { !$0.isEmpty } ?? "未命名"
    }
    var state: String { value["state"].text }
    var source: String { [value["source_name"].text, value["name"].text].first { !$0.isEmpty } ?? "" }
    var sourceFileName: String {
        let raw = [value["source_name"].text, value["name"].text, value["source_path"].text,
                   details["qb_source_path"].text].first { !$0.isEmpty } ?? ""
        return URL(fileURLWithPath: raw).lastPathComponent.nonempty ?? raw
    }
    var poster: String {
        let path = [value["poster"].text, details["media"]["poster_path"].text, details["media"]["poster"].text]
            .first { !$0.isEmpty } ?? ""
        return path.hasPrefix("/") ? "https://image.tmdb.org/t/p/w342" + path : path
    }
    var failure: String {
        let text = [value["failure_message"].text, value["recognition_error"].text,
                    value["error_message"].text].first { !$0.isEmpty } ?? ""
        if text.contains("云端同路径文件") || text.contains("云端目标已存在") { return "云盘中已存在" }
        return text
    }
    var labels: JSONValue {
        details["site_labels"].object.isEmpty ? details["manual_labels"] : details["site_labels"]
    }
    private var expectedFiles: [JSONValue] {
        details["inventory_plan"]["expected_files"].array
    }
    var resolution: String {
        for file in expectedFiles {
            for token in file["recognition"]["resource_tokens"].array.map(\.text) {
                if token.range(of: #"^\d{3,4}p$"#, options: [.regularExpression, .caseInsensitive]) != nil {
                    return token
                }
            }
        }
        return ""
    }
    var mediaCategory: String {
        [value["media_category"].text, details["path_plan"]["category"].text, value["category"].text]
            .first { !$0.isEmpty } ?? ""
    }
    var customization: String {
        var values: [String] = []
        for file in expectedFiles {
            let value = file["recognition"]["customization"].text
            if !value.isEmpty && !values.contains(value) { values.append(value) }
        }
        return values.joined(separator: "@")
    }
    var inventorySummary: String {
        let inventory = details["inventory"]
        let folderStatus = [inventory["folder_status"].text, inventory["folder"]["status"].text,
                            value["inventory_state"].text].first { !$0.isEmpty } ?? ""
        let total = inventory["total_files"].int > 0 ? inventory["total_files"].int :
            (inventory["total"].int > 0 ? inventory["total"].int : expectedFiles.count)
        let existing = inventory["exists_count"].int > 0 ? inventory["exists_count"].int : inventory["exists"].int
        if ["ambiguous", "conflict"].contains(folderStatus) { return "目录冲突" }
        if ["exists", "partial"].contains(folderStatus) || ["exists", "partial"].contains(value["inventory_state"].text) {
            return "目录已存在（\(existing)/\(total)）"
        }
        if total > 0 { return "目录未建立（0/\(total)）" }
        return statusText(folderStatus)
    }
    var inventoryTone: String {
        let inventory = details["inventory"]
        let state = [inventory["folder_status"].text, inventory["folder"]["status"].text,
                     value["inventory_state"].text].first { !$0.isEmpty } ?? ""
        if ["ambiguous", "conflict"].contains(state) { return "warning" }
        if ["exists", "partial"].contains(state) {
            let total = inventory["total_files"].int > 0 ? inventory["total_files"].int :
                (inventory["total"].int > 0 ? inventory["total"].int : expectedFiles.count)
            let existing = inventory["exists_count"].int > 0 ? inventory["exists_count"].int : inventory["exists"].int
            return total > 0 && existing >= total ? "complete" : "missing"
        }
        return "missing"
    }
    var sourceURL: URL? {
        for candidate in [value["comment_url"], value["source_url_masked"], details["rss_source"]["detail_url_masked"],
                          details["comment_url"], details["source_url"]] {
            if let url = safeWebURL(candidate.text) { return url }
        }
        return nil
    }
    var tmdbURL: URL? {
        let tmdb = value["tmdb_id"].int > 0 ? value["tmdb_id"].int : details["manual_override"]["tmdb_id"].int
        let type = value["media_type"].text.nonempty ?? details["manual_override"]["media_type"].text
        return tmdb > 0 ? URL(string: "https://www.themoviedb.org/\(type == "movie" ? "movie" : "tv")/\(tmdb)") : nil
    }
    var identityPayload: JSONValue {
        .object(["downloader_id": value["downloader_id"], "info_hash": value["info_hash"]])
    }
}

func safeWebURL(_ text: String) -> URL? {
    guard var parts = URLComponents(string: text), ["http", "https"].contains(parts.scheme?.lowercased() ?? ""),
          parts.host != nil else { return nil }
    parts.user = nil
    parts.password = nil
    parts.queryItems = parts.queryItems?.filter { !($0.value ?? "").contains("***") }
    return parts.url
}

func sizeText(_ bytes: Double) -> String {
    ByteCountFormatter.string(fromByteCount: Int64(max(0, bytes)), countStyle: .binary)
}

func statusText(_ state: String) -> String {
    [
        "identified": "已识别", "unidentified": "未识别", "pending": "待入库",
        "pending_import": "待入库", "importing": "入库中", "imported": "已入库",
        "existing": "已存在", "exists": "已存在", "rolled_back": "已回退",
        "missing": "缺失", "partial": "不完整", "running": "运行中",
        "queued": "排队中", "completed": "已完成", "succeeded": "已完成", "failed": "失败",
        "recognized": "已识别", "unrecognized": "未识别", "ready": "可处理",
        "filtered": "已过滤", "duplicate": "重复", "invalid": "无效",
        "added": "已添加", "skipped": "已跳过", "content_duplicate": "内容重复",
        "cancelled": "已停止", "error": "异常", "waiting_library": "等待扫库"
    ][state] ?? state
}

extension String {
    var nonempty: String? { isEmpty ? nil : self }
}
