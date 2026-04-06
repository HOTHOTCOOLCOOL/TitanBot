import os
import urllib.request
import zipfile
import subprocess
import shutil

PYTHON_VER = "3.11.9"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VER}/python-{PYTHON_VER}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    runtime_dir = os.path.join(base_dir, "runtime")

    print("===============================================")
    print("构建纯离线 Python Embeddable 运行环境")
    print("===============================================")

    if os.path.exists(runtime_dir):
        print(f"[!] 检测到 runtime 目录已存在，请确认无误后删除或转移它以避免覆盖：\n{runtime_dir}")
        return

    os.makedirs(runtime_dir, exist_ok=True)
    zip_path = os.path.join(base_dir, "python-embed.zip")

    # 1. 下载便携版 Python
    print(f"\n[1/5] 正在下载 Python {PYTHON_VER} 便携免安装版...")
    try:
        urllib.request.urlretrieve(PYTHON_URL, zip_path)
    except Exception as e:
        print(f"[错误] 无法从官网下载Python，请检查网络（如果国内无法直连，请使用学术上网）：{e}")
        return

    # 2. 解压缩
    print("[2/5] 正在解压至 runtime 目录...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(runtime_dir)
    os.remove(zip_path)

    # 3. 启用 site-packages 导入
    # 这一步极其重要！Embed版默认是隔离的，无法使用第三方包(pip)，必须把 #import site 的注释解开
    print("[3/5] 配置底层引擎 (修改 ._pth 解除隔离)...")
    ver_prefix = "".join(PYTHON_VER.split(".")[:2]) # "3.11.9" -> "311"
    pth_file = os.path.join(runtime_dir, f"python{ver_prefix}._pth")
    if os.path.exists(pth_file):
        with open(pth_file, "r") as f:
            content = f.read()
        content = content.replace("#import site", "import site")
        with open(pth_file, "w") as f:
            f.write(content)

    # 4. 植入 Pip
    print("[4/5] 正在下载并给免安装环境注入 pip 工具...")
    pip_script = os.path.join(runtime_dir, "get-pip.py")
    try:
        urllib.request.urlretrieve(GET_PIP_URL, pip_script)
    except Exception as e:
        print(f"[错误] 下载 get-pip 失败：{e}")
    
    python_exe = os.path.join(runtime_dir, "python.exe")
    print("    -> 正在执行安装，这大概需要十几秒...")
    subprocess.run([python_exe, pip_script], check=True)
    
    # 5. 调用免安装版的 pip 下载核心依赖
    print("\n[5/5] 开始安装您的项目所有依赖！ (全部锁定注入到 runtime 内)")
    req_path = os.path.join(base_dir, "requirements.txt")
    if not os.path.exists(req_path):
        print(f"[警告] 未在根目录找到 requirements.txt，跳过依赖安装。您后续可以通过 runtime\python.exe -m pip install 进行扩充。")
    else:
        # 使用清华源在国内极速下载
        print("    -> 正在通过清华镜像将 requirements.txt 集成到黑盒中...")
        subprocess.run([
            python_exe, "-m", "pip", "install", 
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", 
            "-r", req_path
        ], check=True)

    print("\n===============================================")
    print("✨ 创建完毕！")
    print("===============================================")
    print(f"您的绿色生态环境已经构建在: {runtime_dir}")
    print("现在，只要您把整个项目打成 zip 压缩包发给另一台 Windows 电脑，不论对方有没有装过 Python，双击 start_portable.bat 均可完美运行！")

if __name__ == "__main__":
    main()
