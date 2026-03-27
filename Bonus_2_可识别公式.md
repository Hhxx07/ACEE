2026-03-27


代码能够识别的自然语言及其对应的“公式”：
### 1. 核心操作指令 (意图与命令映射)
只要输入中包含以下**自然语言关键词**，代码就会将其识别为特定的意图（Intent），并根据当前操作系统（Windows 或 Linux/Mac）生成对应的命令。

| 意图 (Intent) | 可识别的自然语言关键词 | 生成的 Windows 命令 | 生成的 Linux/Mac 命令 |
| :--- | :--- | :--- | :--- |
| **显示当前目录**<br>(show_cwd) | `"当前目录", "pwd", "where am i"` | `cd` | `pwd` |
| **列出文件**<br>(list_files) | `"列出", "文件列表", "ls", "dir", "list files"` | `dir` | `ls -la` |
| **读取/查看文件**<br>(read_file) | `"查看文件", "读取文件", "cat", "type", "open file"` | `type "目标文件"` | `cat "目标文件"` |
| **创建目录**<br>(make_dir) | `"创建目录", "新建目录", "mkdir", "make dir"` | `mkdir "目标目录"` | `mkdir -p "目标目录"` |
| **系统信息**<br>(system_info) | `"系统信息", "系统版本", "uname", "ver", "os 信息"` | `ver` | `uname -a` |
| **网络信息**<br>(network_info)| `"网络", "端口", "ip", "netstat", "ifconfig"` | `netstat -ano` | `netstat -an` |
| **进程列表**<br>(process_list)| `"进程列表", "ps", "tasklist", "查看进程"` | `tasklist` | `ps aux` |
| **结束进程**<br>(kill_process)| `"结束进程", "杀进程", "kill", "taskkill"`<br>*(需配合 PID)* | `taskkill /PID {pid}` | `kill {pid}` |
| **搜索文件**<br>(search_files)| `"查找", "搜索", "find", "grep", "搜索文件"` | **带扩展名:** `dir /s /b *.{ext}`<br>**不带扩展名:** `dir /s /b` | **带扩展名:** `find . -type f -name '*.{ext}'`<br>**不带扩展名:** `find . -maxdepth 3 -type f` |
| **移动/重命名**<br>(move) | `"移动", "重命名", "mv", "move", "rename"`<br>*(必须包含关键字 **" 到 "**)* | `move "源路径" "目标路径"` | `mv -i "源路径" "目标路径"` |
| **删除文件/目录**<br>(delete) | `"删除", "移除", "清空", "rm", "del", "remove"` | **非递归:** `del "目标"`<br>**递归:** `powershell ... Remove-Item ... -Recurse -Confirm` | **非递归:** `rm -i "目标"`<br>**递归:** `rm -ri "目标"` |

---

### 2. 参数提取规则 (目标、PID、扩展名)
通过正则表达式从自然语言中提取操作对象（参数）：

*   **目标路径提取 (`_extract_path`)**
    *   **前缀引导：** 识别 `文件:`、`目录:`、`路径:`、`folder:`、`file:` 后面的路径。
    *   **绝对/相对路径：** 直接识别 `C:\xxx`、`./xxx`、`/xxx` 这种标准路径格式。
    *   **特定后缀文件：** 直接识别带有常见后缀的文件名（如 `test.py`, `config.json`, `data.csv` 等）。
*   **文件扩展名提取 (`_extract_extension`)**
    *   识别输入中包含的特定后缀类型：`.py`, `.txt`, `.md`, `.json`, `.log`, `.csv`, `.yaml`, `.yml`, `.ini`, `.cfg`。（用于 `search_files` 生成带有 `*.ext` 的搜索公式）。
*   **进程号 (PID) 提取 (`_extract_pid`)**
    *   识别 `pid: 1234`、`pid 1234` 或者**直接识别 2 到 7 位的纯数字**。（用于 `kill_process`）。
*   **移动路径分割 (针对 `move`)**
    *   使用中文的 `" 到 "` 作为分隔符。例如输入：“把 ./a.txt **到** ./b.txt”，代码会把前半部分识别为源文件，后半部分提取为目标文件。

---

### 3. 操作修饰词语 (影响命令公式或风险评级)
识别修饰词改变最终的公式或者影响操作的安全评估（Risk Score）：

| 修饰类型 | 可识别的自然语言 / 符号 | 对应的公式改变或影响 |
| :--- | :--- | :--- |
| **递归执行** (Recursive) | `"递归", "recursive", "-r", "/s"` | **改变公式**：<br>Linux 删除从 `rm -i` 变为 `rm -ri`<br>Win 删除变为 `powershell ... -Recurse` |
| **强制执行** (Forced) | `"强制", "force", "-f", "/f"` | 不改变最终公式（为了安全，代码里的删除写死了带 `-i` 或 `-Confirm`），但会**增加危险分数** (+0.18) |
| **权限操作** (Privilege) | `"sudo", "管理员", "admin", "root"` | 增加危险分数 (+0.22) |
| **大范围/敏感目标** | `"*" , "all files", "全部文件", "整个目录", "根目录", "/", "c:\windows"` | 增加危险分数 (+0.18 或 +0.25) |
| **命令注入风险** | `";" , "&&", "\|\|", "$(", "\`"` | 极大地增加危险分数 (+0.35) |
