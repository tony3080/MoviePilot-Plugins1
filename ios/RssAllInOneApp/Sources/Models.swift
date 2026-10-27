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
        case .number(let value): return value.formatted(.number.grouping(.never))
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
        if !value["id"].text.isEmpty { return value["id"].text }
        return value["downloader_id"].text + ":" + value["info_hash"].text
    }
    subscript(_ key: String) -> JSONValue { value[key] }
    var details: JSONValue { value["details"] }
    var title: String {
        [value["media_title"].text, value["title"].text, value["name"].text,
         value["source_name"].text].first { !$0.isEmpty } ?? "未命名"
    }
    var state: String { value["state"].text }
    var source: String { [value["source_name"].text, value["name"].text].first { !$0.isEmpty } ?? "" }
    var poster: String {
        let path = [value["poster"].text, details["media"]["poster_path"].text].first { !$0.isEmpty } ?? ""
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
    var sourceURL: URL? {
        for candidate in [value["comment_url"], value["source_url_masked"], details["rss_source"]["detail_url_masked"],
                          details["comment_url"], details["source_url"]] {
            if let url = safeWebURL(candidate.text) { return url }
        }
        return nil
    }
    var tmdbURL: URL? {
        let tmdb = value["tmdb_id"].int
        return tmdb > 0 ? URL(string: "https://www.themoviedb.org/\(value["media_type"].text == "movie" ? "movie" : "tv")/\(tmdb)") : nil
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
        "queued": "排队中", "completed": "已完成", "failed": "失败",
        "cancelled": "已停止", "error": "异常", "waiting_library": "等待扫库"
    ][state] ?? state
}

extension String {
    var nonempty: String? { isEmpty ? nil : self }
}
