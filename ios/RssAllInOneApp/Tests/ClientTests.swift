import Foundation
import Testing
@testable import RssAllInOneApp

@Suite("Client contracts", .serialized)
struct ClientTests {
    @Test func preservesUnknownConfigurationFields() throws {
        let data = Data(#"{"config":{"enabled":true,"future":{"x":[1,"二",null]}},"tmdb_id":42}"#.utf8)
        var value = try JSONDecoder().decode(JSONValue.self, from: data)
        var config = value["config"]
        config["enabled"] = .bool(false)
        value["config"] = config
        let decoded = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(value))
        #expect(decoded["config"]["future"]["x"].array.count == 3)
        #expect(decoded["tmdb_id"].text == "42")
        #expect(decoded["config"]["enabled"].flag == false)
    }

    @Test func cardIdentityIncludesDownloaderAndHash() {
        let a = Record(value: .object(["downloader_id": .string("A"), "info_hash": .string("hash")]))
        let b = Record(value: .object(["downloader_id": .string("B"), "info_hash": .string("hash")]))
        #expect(a.id != b.id)
        #expect(a.identityPayload["info_hash"].text == "hash")
    }

    @Test func downloadersWithoutNumericIDsHaveDistinctIdentities() {
        let a = Record(value: .object(["name": .string("SSD")]))
        let b = Record(value: .object(["name": .string("UP")]))
        #expect(a.id != b.id)
    }

    @Test func numberIDsKeepAllDigitsAndDoNotUseLocaleGrouping() {
        #expect(JSONValue.number(123456789).text == "123456789")
        #expect(JSONValue.number(1.25).text == "1.25")
    }

    @Test func legacySettingsKeepUnknownFieldsAndEditableRouteStructure() throws {
        let input = Data(#"{"future_flag":true,"cd2_token":"secret","source_routes":"[{\"name\":\"A\",\"prefix\":\"/A\",\"link_roots\":{\"default\":\"/link\"}}]"}"#.utf8)
        let original = try JSONDecoder().decode(JSONValue.self, from: input)
        let normalized = PluginDefaults.normalized(original)
        #expect(normalized["future_flag"].flag)
        #expect(normalized["cd2_token"].text == "secret")
        #expect(normalized["source_routes"].array.first?["enabled"].flag == true)
        #expect(normalized["source_routes"].array.first?["link_roots"]["default"].text == "/link")
    }

    @Test(arguments: ["http://nas:3033", "http://nas:3033/api/v1", "http://nas:3033/"])
    func buildsPluginURL(_ base: String) throws {
        let client = APIClient(config: ServerConfig(baseURL: base))
        let url = try client.url("plugin/RssAllInOne/media", query: [.init(name: "rss_task_ids", value: "a,b")])
        #expect(url.path == "/api/v1/plugin/RssAllInOne/media")
        #expect(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first?.value == "a,b")
    }

    @Test func keepsReverseProxyPrefixAndRejectsEmbeddedCredentials() throws {
        let client = APIClient(config: ServerConfig(baseURL: "https://nas/mp/"))
        #expect(try client.url("plugin/RssAllInOne").path == "/mp/api/v1/plugin/RssAllInOne")
        #expect(throws: APIError.self) {
            try APIClient(config: ServerConfig(baseURL: "https://name:password@nas")).url("overview")
        }
    }

    @Test func sourceLinkRemovesMaskedSecretsAndRejectsOtherSchemes() {
        #expect(safeWebURL("javascript:alert(1)") == nil)
        let url = safeWebURL("https://pt.example/details.php?id=123&passkey=***")
        #expect(url?.query == "id=123")
        #expect(safeWebURL("https://user:password@pt.example/details.php?id=1")?.user == nil)
    }

    @Test func showsCloudConflictAsExisting() {
        let card = Record(value: .object(["failure_message": .string("云端同路径文件大小不一致：本地=1，云端=2")]))
        #expect(card.failure == "云盘中已存在")
    }

    @Test func sendsStableIdentitiesAndBearerAuthentication() async throws {
        let session = testSession()
        MockProtocol.handler = { request in
            #expect(request.url?.path == "/api/v1/plugin/RssAllInOne/media/mark-unidentified")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer sample-token")
            #expect(request.httpMethod == "POST")
            return (200, #"{"success":true,"message":"done"}"#)
        }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas", token: "sample-token"), session: session)
        let result = try await client.send("media/mark-unidentified", body: .object(["media_id": .string("qb:a:hash")]))
        #expect(result["success"].flag)
    }

    @Test func applicationFailuresAreNotTreatedAsSuccess() async throws {
        MockProtocol.handler = { _ in (200, #"{"success":false,"message":"not allowed"}"#) }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas"), session: testSession())
        do { _ = try await client.send("media/action"); Issue.record("Expected failure") }
        catch { #expect(error.localizedDescription == "not allowed") }
    }

    @Test func expiredLoginRequiresAuthentication() async throws {
        MockProtocol.handler = { _ in (401, #"{"detail":"expired"}"#) }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas"), session: testSession())
        do { _ = try await client.get("overview"); Issue.record("Expected unauthorized") }
        catch APIError.unauthorized {} catch { Issue.record("Unexpected error: \(error)") }
    }

    @Test func healthViewCanReadFailureDiagnostics() async throws {
        MockProtocol.handler = { _ in (200, #"{"success":false,"startup_error":"SQLite unavailable"}"#) }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas"), session: testSession())
        let reply = try await client.get("health", diagnostic: true)
        #expect(reply["startup_error"].text == "SQLite unavailable")
    }

    @Test func loginEncodesLiteralPlusAndIncludesOTP() async throws {
        MockProtocol.handler = { request in
            #expect(request.url?.path == "/api/v1/login/access-token")
            #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
            let body = Self.body(request)
            #expect(body.contains("password=p%2Ba"))
            #expect(body.contains("otp_password=123456"))
            return (200, #"{"access_token":"new-token"}"#)
        }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas"), session: testSession())
        #expect(try await client.login(username: "me", password: "p+a", otp: "123456") == "new-token")
    }

    @Test func fullTaskSnapshotLoadsEveryPage() async throws {
        MockProtocol.handler = { request in
            let items = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
            if items.first(where: { $0.name == "offset" })?.value == "0" {
                return (200, #"{"items":[{"id":"a"}],"total":2}"#)
            }
            return (200, #"{"items":[{"id":"b"}],"total":2}"#)
        }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas"), session: testSession())
        #expect(try await client.allTasks().map { $0["id"].text } == ["a", "b"])
    }

    @Test func partialFailuresKeepServerSummaryAndIndividualReason() async throws {
        MockProtocol.handler = { _ in
            (200, #"{"success":false,"partial":true,"message":"部分完成","results":[{"success":true},{"success":false,"message":"被保护"}]}"#)
        }
        let client = APIClient(config: ServerConfig(baseURL: "http://nas"), session: testSession())
        do { _ = try await client.send("media/action"); Issue.record("Expected partial failure") }
        catch { #expect(error.localizedDescription == "部分完成\n被保护") }
    }

    private static func body(_ request: URLRequest) -> String {
        if let data = request.httpBody { return String(decoding: data, as: UTF8.self) }
        guard let stream = request.httpBodyStream else { return "" }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var bytes = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
            let count = stream.read(&bytes, maxLength: bytes.count)
            if count <= 0 { break }
            data.append(contentsOf: bytes.prefix(count))
        }
        return String(decoding: data, as: UTF8.self)
    }

    private func testSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        return URLSession(configuration: configuration)
    }
}

final class MockProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var callback: ((URLRequest) -> (Int, String))?
    static var handler: ((URLRequest) -> (Int, String))? {
        get { lock.lock(); defer { lock.unlock() }; return callback }
        set { lock.lock(); defer { lock.unlock() }; callback = newValue }
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = Self.handler, let url = request.url else { return }
        let (status, body) = handler(request)
        guard let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
