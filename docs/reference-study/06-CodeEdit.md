# CodeEdit — 现代 IDE 框架（SwiftUI 参考）

> **源码位置**: `D:\code\codeedit` | **大小**: 11 MB | **语言**: Swift  
> **官网**: https://github.com/CodeEditApp/CodeEdit | **Stars**: ~15k+  
> **定位**: 用 SwiftUI 构建的现代 IDE 模板，展示 IDE 应有的标准 UI 结构

---

## 一、项目概览

CodeEdit 是一个 **macOS 原生 IDE**，用 Apple 的 SwiftUI 框架构建。虽然我们用的是 Vue + Tauri（跨平台），但 CodeEdit 展示了 **IDE UI 的标准组件和布局模式**：

📁 **Project Navigator** — 文件树浏览器
📑 **Editor Tab 管理** — 多文件标签页切换
🔧 **Settings 架构** — 分层设置系统
🎨 **主题系统** — 完整的亮色/暗色/自定义主题

### 为什么看它？
CodeEdit 比 VS Code 简单得多（11MB vs 220MB），是理解 **IDE UI 组件组成**的最佳入门项目。

---

## 二、目录结构

```
D:\code\codeedit\
├── CodeEdit/
│   ├── App/                       # 应用入口
│   │   └── CodeEditApp.swift      #    AppDelegate
│   ├── AppDelegate/               # 代理
│   ├── Documents/                 # 文档管理
│   ├── Extensions/                # Swift 扩展
│   ├── KeyboardShortcuts/         # 快捷键
│   ├── Models/                    # ★★★ 数据模型
│   │   ├── AppState.swift         #    全局状态 ⭐
│   │   ├── WorkspaceDocument.swift #    工作区文档
│   │   ├── WorkspaceClient.swift  #    工作区客户端
│   │   ├── FileItem.swift         #    ★★ 文件树节点模型 ⭐
│   │   ├── Editor.swift           #    编辑器状态
│   │   └── Settings/              #    设置数据模型
│   │       ├── Settings.swift     #    设置实体
│   │       └── ...
│   ├── Observed/                  # 观察者模式实现
│   ├── Scenes/                    # 场景
│   ├── Utility/                   # 工具函数
│   ├── Views/                     # ★★★ UI 视图 ⭐⭐⭐
│   │   ├── ContentView.swift      #    根视图（主窗口）
│   │   ├── Sidebar/               #    ★ 侧边栏视图
│   │   │   ├── SidebarView.swift #       主侧边栏
│   │   │   ├── SidebarToolbar.swift #    工具栏
│   │   │   └── ProjectNavigator/        # ★★ 项目导航器 ⭐⭐
│   │   │       ├── ProjectNavigatorView.swift
│   │   │       └── ProjectNavigatorItemView.swift
│   │   ├── Editor/                #    ★ 编辑器区域 ⭐⭐
│   │   │   ├── EditorView.swift  #       编辑器容器
│   │   │   ├── TabBar/            #       标签页
│   │   │   │   ├── TabBarView.swift
│   │   │   │   └── TabBarItemView.swift
│   │   │   └── ...
│   │   ├── Settings/              #    ★ 设置界面 ⭐
│   │   │   ├── SettingsView.swift #       设置主页面
│   │   │   └── 各个设置子页面...
│   │   ├── Toolbar/               #    顶部工具栏
│   │   ├── Terminal/              #    终端视图
│   │   └── WelcomeScreen/         #    欢迎/打开项目页面
│   └── ...
├── CodeEdit.xcodeproj/
└── README.md
```

---

## 三、核心设计模式

### 3.1 FileItem 数据模型（文件树）

```swift
// Models/FileItemItem.swift — 文件树的节点结构
class FileItem: Identifiable {
    var id: String { url.path }
    var url: URL              // 文件路径
    var name: String          // 显示名称 (如 "main.ts")
    var children: [FileItem]? // 子项（文件夹有，文件无）
    var icon: Icon?           // 图标（根据扩展名决定）
    var kind: FileItemKind    // .file | .folder | .symlink
    
    // 计算属性：
    var isDirectory: Bool { children != nil }
    var fileExtension: String { url.pathExtension.lowercased() }
    
    // 方法：
    func sortChildren() -> [FileItem]  // 排序：文件夹在前 → 字母序
}
```

**对应我们的 Vue 类型**:
```typescript
// studio-client 的 TreeNode 或新定义的 ReferencedFile
interface FileNode {
  path: string;
  name: string;
  type: 'file' | 'directory';
  language?: string;
  children?: FileNode[];
  icon?: string; // vscode-icons 对应的图标名
}
```

### 3.2 Project Navigator UI（侧边栏文件树）

```swift
// Views/Sidebar/ProjectNavigator/ProjectNavigatorView.swift
struct ProjectNavigatorView: View {
    @ObservedObject var workspace: WorkspaceClient
    
    var body: some View {
        VStack(spacing: 0) {
            // 1. 工具栏：搜索 + 过滤 + 操作按钮
            toolbar
            
            // 2. 文件列表（Outline Group = macOS 原生树形控件）
            OutlineGroup(workspace.fileItems, children: \.children) { item in
                // 文件夹：可展开
                if item.isDirectory {
                    Label(item.name, systemImage: "folder")
                        .foregroundColor(.secondary)
                        .tag(item)
                } else {
                    // 文件：显示语言对应的图标
                    HStack {
                        Image(nsImage: NSWorkspace.shared.icon(forFileType: item.fileExtension))
                            .resizable().frame(width: 16, height: 16)
                        Text(item.name)
                            .font(.system(.body, design: .monospaced))
                        Spacer()
                    }
                    .tag(item)
                    .contextMenu { /* 右键菜单 */ }  // ← 重要！右键操作
                    .onTapGesture(count: 2) { /* 双击打开 */ }
                }
            }
            
            // 底部信息栏
            footer
        }
    }
}
```

**右键菜单内容**:
```
Open          → 打开编辑
Open With...   → 选择外部程序打开
Show in Finder → 在访达中定位
Copy Path      → 复制完整路径
Copy Name      → 复制文件名
─────────────
New File       → 新建文件
New Folder     → 新建文件夹
─────────────
Rename         → 重命名
Delete         → 删除（移到废纸篓）
```

**我们的落地**: 文件树右键添加 "@引用到对话" 选项

### 3.3 Editor Tab Bar

```swift
// Views/Editor/TabBar/TabBarView.swift
struct TabBarView: View {
    @Binding var openFiles: [Editor]  // 当前打开的所有文件
    
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 0) {
                ForEach(openFiles) { editor in
                    TabBarItemView(editor: editor)
                        .onTapGesture { selectTab(editor) }
                        // 关闭按钮（中间点击或 x 按钮）
                        .contextMenu {
                            Button("Close Others") { closeOthers(except: editor) }
                            Button("Close All") { closeAll() }
                            Divider()
                            Button("Copy Path") { copyPath(editor.url) }
                            Button("Reveal in Finder") { revealInFinder(editor.url) }
                        }
                }
                
                // "+" 按钮：新建文件
                Button(action: newFile) {
                    Image(systemName: "plus").font(.caption)
                }
            }
            .padding(.horizontal, 8)
            .frame(height: 32)  // 固定高度
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

// 单个 Tab 项
struct TabBarItemView: View {
    let editor: Editor
    @State var isHovered = false
    
    var body: some View {
        HStack(spacing: 4) {
            // 文件图标（小尺寸）
            Image(nsFileIcon)
                .resizable()
                .frame(width: 14, height: 14)
            
            // 文件名
            Text(editor.name)
                .lineLimit(1)
                .font(.system(size: 12))
            
            // 未保存指示点（修改过但未保存时显示圆点）
            if editor.isModified {
                Circle()
                    .fill(Color.orange)
                    .frame(width: 6, height: 6)
            }
            
            // 关闭按钮（hover 时显示）
            if isHovered {
                Button(action: { close(editor) }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 9))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(isActive ? selectedBg : clearBg)
        .cornerRadius(6)
        .onHover { hovering in isHovered = hovering }
    }
}
```

### 3.4 Settings 分层架构

```
SettingsView
├── General          — 通用设置（外观、行为）
│   ├── Appearance    —  主题选择（Light/Dark/System）
│   ├── Font          —  编辑器字体
│   └── Behavior      —  行为偏好（自动保存等）
├── Editor            — 编辑器设置
│   ├── Font & Color  —  字体大小、行号等
│   ├── Indentation   —  缩进风格（Tab/空格/宽度）
│   └── Display       —  折行、 minimap、渲染空白字符
├── Terminal          — 终端设置
│   └── Shell / Font / Opacity
├── Keybindings       — 快捷键配置
├── Accounts          — 账号（Git 等）
└── Advanced          — 高级选项
    ├── Telemetry     —  遥测开关
    └── Reset          —  重置所有设置
```

---

## 四、值得借鉴的点

| 设计 | CodeEdit 实现 | 我们的落地 |
|------|--------------|-----------|
| 文件树 | `ProjectNavigatorView` + `OutlineGroup` | Vue Tree 组件 |
| 右键菜单 | `.contextMenu` 含 Open/Copy/Rename/Delete | 加上 "@引用到对话" |
| Tab Bar | 可关闭、未保存指示、右键关闭其他 | 编辑器标签页 |
| Settings | 分层分类、搜索过滤 | Tauri 设置面板 |
| 主题 | Light/Dark/System + 自定义颜色 | 已支持暗色模式 |

---

## 五、快速入门

```bash
cd D:\code\codeedit
# 需要 XCode 打开 .xcodeproj 编译运行
# 或者用 Xcode Build 直接 build
```
