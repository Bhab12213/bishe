from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_simple():
    # 直接返回纯文本，无任何额外操作，避免阻塞
    return "8080端口服务正常，无阻塞！"

if __name__ == "__main__":
    # 与你的服务配置一致，关闭调试模式
    app.run(host='0.0.0.0', port=8080, debug=False)