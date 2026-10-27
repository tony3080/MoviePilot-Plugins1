import SwiftUI

struct FilesView: View {
    @EnvironmentObject private var store: AppStore
    let path: String
    @State private var listing: JSONValue = .null
    @State private var search = ""
    @State private var selected: JSONValue?
    @State private var batch = false
    @State private var loading = false
    @State private var taskID: String?

    private var entries: [JSONValue] {
        listing["items"].array.filter { search.isEmpty || $0["name"].text.localizedCaseInsensitiveContains(search) }
    }
    var body: some View {
        List {
            Section {
                Text(path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                if let taskID {
                    NavigationLink { TaskDetailView(id: taskID) } label: { Label("查看识别进度", systemImage: "clock") }
                }
            }
            ForEach(entries.indices, id: \.self) { index in
                let entry = entries[index]
                HStack {
                    if entry["type"].text == "dir" {
                        NavigationLink { FilesView(path: entry["path"].text) } label: {
                            Label(entry["name"].text, systemImage: "folder").foregroundStyle(.primary)
                        }
                    } else {
                        Label(entry["name"].text, systemImage: "film").foregroundStyle(.primary)
                    }
                    Button { selected = entry } label: { Image(systemName: "viewfinder") }
                        .buttonStyle(.borderless).accessibilityLabel("识别 \(entry["name"].text)")
                }
            }
            if loading { ProgressView().frame(maxWidth: .infinity) }
        }
        .navigationTitle(path == "/" ? "文件管理" : (path as NSString).lastPathComponent)
        .navigationBarTitleDisplayMode(path == "/" ? .large : .inline)
        .searchable(text: $search, prompt: "搜索当前目录")
        .toolbar {
            Menu {
                Button("批量识别当前目录", systemImage: "viewfinder") { batch = true }
                Button("刷新", systemImage: "arrow.clockwise") { Task { await load() } }
            } label: { Image(systemName: "ellipsis.circle") }
        }
        .task { await load() }
        .refreshable { await load() }
        .confirmationDialog("识别所选项目？", isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } }), titleVisibility: .visible) {
            Button("识别") {
                let target = selected?["path"] ?? .null
                Task {
                    await store.perform("files/recognize", body: .object(["path": target]))
                    selected = nil
                }
            }
        } message: { Text(selected?["name"].text ?? "") }
        .confirmationDialog("批量识别当前目录？", isPresented: $batch, titleVisibility: .visible) {
            Button("开始识别") {
                Task {
                    let response = await store.perform("files/recognize-batch", body: .object(["path": .string(path)]))
                    taskID = response?["task_id"].text
                }
            }
        }
        .safeAreaInset(edge: .bottom) { OperationNotice() }
        .disabled(store.busy)
    }
    private func load() async {
        loading = true; defer { loading = false }
        do { listing = try await store.client.get("files/browse", query: [.init(name: "path", value: path)]) }
        catch { store.report(error) }
    }
}

struct TaskRow: View {
    let item: Record
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(item["task_name"].text.nonempty ?? item["task_type"].text).font(.headline)
                Spacer()
                StatusBadge(state: item.state)
            }
            if item["total"].int > 0 { ProgressView(value: item["processed"].double, total: item["total"].double) }
            Text("\(item["processed"].int)/\(item["total"].int) · \(item["updated_at"].text)")
                .font(.caption).foregroundStyle(.secondary)
            if !item["current_item"].text.isEmpty { Text(item["current_item"].text).font(.caption).lineLimit(2) }
            if !item.failure.isEmpty { Text(item.failure).font(.caption).foregroundStyle(.red).lineLimit(3) }
        }
    }
}

struct TaskListView: View {
    @EnvironmentObject private var store: AppStore
    @StateObject private var page = PageStore()
    @State private var clear = false
    var body: some View {
        List {
            ForEach(page.rows) { task in
                NavigationLink { TaskDetailView(id: task.id) } label: { TaskRow(item: task) }
            }
            PageFooter(page: page) { await load(more: true) }
            if page.rows.isEmpty && !page.loading { ContentUnavailableView("没有失败任务", systemImage: "checkmark.circle") }
        }
        .navigationTitle("后台任务")
        .toolbar { Button { clear = true } label: { Image(systemName: "trash") }.accessibilityLabel("清空失败记录") }
        .confirmationDialog("清空所有失败后台任务记录？", isPresented: $clear, titleVisibility: .visible) {
            Button("清空失败记录", role: .destructive) { Task { await store.perform("tasks/clear"); await load() } }
        }
        .task(id: store.generation) { await load() }.refreshable { await load() }
    }
    private func load(more: Bool = false) async {
        do { try await page.load(store.client, path: "tasks", more: more) } catch { store.report(error) }
    }
}

struct TaskDetailView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    let id: String
    @State private var task: JSONValue = .null
    var body: some View {
        List {
            Section { TaskRow(item: Record(value: task)) }
            Section { JSONDetails(value: task) }
        }
        .navigationTitle("任务进度")
        .refreshable { await load() }
        .task(id: "\(scenePhase)-\(store.generation)") {
            guard scenePhase == .active else { return }
            await load()
            while !Task.isCancelled && ["queued", "running"].contains(task["state"].text) {
                do { try await Task.sleep(for: .seconds(3)) } catch { return }
                await load()
            }
        }
    }
    private func load() async {
        do { task = try await store.client.get("tasks/\(id)")["task"] } catch { store.report(error) }
    }
}

struct ImportStatusView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var status: JSONValue = .null
    @State private var action = ""
    @State private var confirming = false
    @State private var switches: JSONValue = .object([:])
    var body: some View {
        List {
            Section("当前进度") { JSONDetails(value: status) }
            Section("入库") {
                Button("立刻处理待入库", systemImage: "play.circle") { action = "import/run"; confirming = true }
                Button("结束等待扫库完成", systemImage: "stop.circle") { action = "import/wait/cancel"; confirming = true }
            }
            Section("外部开关") {
                ForEach(["catchup", "scan"], id: \.self) { key in
                    HStack {
                        Text(key == "catchup" ? "追更" : "SA 扫库")
                        Spacer()
                        if switches[key] != .null { Text(switches[key]["enabled"].flag ? "开启" : "关闭").foregroundStyle(.secondary) }
                        Button("读取") { Task { await control(key, toggle: false) } }
                        Button("切换") { action = "external/\(key)/control"; confirming = true }
                    }
                }
            }
        }
        .navigationTitle("入库进度")
        .disabled(store.busy)
        .confirmationDialog("确认执行此操作？", isPresented: $confirming, titleVisibility: .visible) {
            Button("确认") {
                Task {
                    if action.hasPrefix("external/") {
                        await control(action.contains("catchup") ? "catchup" : "scan", toggle: true)
                    } else { await store.perform(action); await load() }
                }
            }
        }
        .refreshable { await load() }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await load()
            while !Task.isCancelled && status["running"].flag {
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
                await load()
            }
        }
    }
    private func control(_ key: String, toggle: Bool) async {
        if let reply = await store.perform("external/\(key)/control", body: .object(["action": .string(toggle ? "toggle" : "read")])) {
            switches[key] = reply
        }
    }
    private func load() async {
        do { status = try await store.client.get("import/status") } catch { store.report(error) }
    }
}

struct HistoryView: View {
    @EnvironmentObject private var store: AppStore
    @StateObject private var page = PageStore()
    var body: some View {
        List {
            ForEach(page.rows) { item in
                NavigationLink {
                    List { JSONDetails(value: item.value) }.navigationTitle(item.title)
                } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.title).font(.headline)
                        HStack { StatusBadge(state: item.state); Text(item["created_at"].text).font(.caption).foregroundStyle(.secondary) }
                    }
                }
            }
            PageFooter(page: page) { await load(more: true) }
        }
        .navigationTitle("RSS 历史").task { await load() }.refreshable { await load() }
    }
    private func load(more: Bool = false) async {
        do { try await page.load(store.client, path: "rss/history", more: more) } catch { store.report(error) }
    }
}

struct SiteListView: View {
    @EnvironmentObject private var store: AppStore
    @State private var sites: [Record] = []
    var body: some View {
        List(sites) { site in
            NavigationLink {
                List { JSONDetails(value: site.value) }.navigationTitle(site.title)
            } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(site.title).font(.headline)
                    Text(site["domain"].text).font(.caption).foregroundStyle(.secondary)
                    Text("\(site["auth_mode"].text) · \(site["ready"].flag ? "就绪" : "未就绪")").font(.caption)
                }
            }
        }.navigationTitle("站点身份").task { await load() }.refreshable { await load() }
    }
    private func load() async {
        do { sites = try await store.client.get("sites")["items"].array.map { Record(value: $0) } }
        catch { store.report(error) }
    }
}
