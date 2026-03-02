from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
import sqlite3
import re
from datetime import datetime
from functools import wraps
import time
import requests  # 新增：导入requests库用于调用GLM API

# ====================== 需手动配置的密钥 ======================
GLM_API_KEY = "11111"  # 请替换为实际的API Key
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"  # GLM-4-Flash接口地址
# =============================================================

# 1. 初始化Flask应用
app = Flask(__name__)

# 配置项（关键）
app.config['SECRET_KEY'] = 'campus_secondhand_123'  # 用于flash消息提示和session
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # 图片上传目录
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制图片大小（16MB）
app.config['DEFAULT_IMAGE'] = 'static/images/default.png'  # 默认图片路径

# 允许上传的图片格式
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


# 2. 辅助函数：判断文件格式是否合法
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# 3. 辅助函数：初始化SQLite数据库（修复示例数据图片路径）
def init_db():
    """初始化数据库，创建所有表、索引和示例数据"""

    # 确保目录存在
    os.makedirs(os.path.dirname(app.config['DEFAULT_IMAGE']), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    conn = sqlite3.connect('secondhand.db')
    c = conn.cursor()

    print("正在初始化数据库...")

    # 创建用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  password TEXT NOT NULL,
                  email TEXT,
                  user_type TEXT NOT NULL DEFAULT 'normal',
                  register_time TEXT NOT NULL,
                  last_login TEXT)''')

    # 创建商品表（包含user_id关联用户）
    c.execute('''CREATE TABLE IF NOT EXISTS goods
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  price REAL NOT NULL,
                  category TEXT NOT NULL,
                  description TEXT,
                  image TEXT,
                  publish_time TEXT NOT NULL,
                  user_id INTEGER)''')

    # 为description和title字段创建全文搜索索引
    c.execute("CREATE INDEX IF NOT EXISTS idx_goods_description ON goods(description)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_goods_title ON goods(title)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_goods_category ON goods(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_goods_user ON goods(user_id)")

    print("数据表创建完成...")

    # 添加默认管理员和测试用户（如果不存在）
    try:
        c.execute(
            "INSERT OR IGNORE INTO users (username, password, email, user_type, register_time) VALUES (?, ?, ?, ?, ?)",
            ('admin', 'admin123', 'admin@example.com', 'admin', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        # c.execute(
        #     "INSERT OR IGNORE INTO users (username, password, email, user_type, register_time) VALUES (?, ?, ?, ?, ?)",
        #     ('user1', 'user123', 'user1@example.com', 'normal', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        # c.execute(
        #     "INSERT OR IGNORE INTO users (username, password, email, user_type, register_time) VALUES (?, ?, ?, ?, ?)",
        #     ('user2', 'user123', 'user2@example.com', 'normal', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        print("默认用户创建完成...")
    except Exception as e:
        print(f"初始化默认用户失败: {e}")

    # 检查是否有商品数据，如果没有则插入示例数据
    c.execute("SELECT COUNT(*) FROM goods")
    goods_count = c.fetchone()[0]

    if goods_count == 0:
        print("正在插入示例商品数据...")
        # 插入示例商品数据（只存储图片文件名，不包含路径）
        example_goods = [
            ('二手笔记本电脑', 2999.00, '电子设备',
             'ThinkPad X1 Carbon，8代i5处理器，8GB内存，256GB SSD，13.3英寸屏幕，轻便便携，适合学习和办公',
             None, '2025-01-15 10:30:00', 2),  # 使用默认图片
            ('红色运动鞋', 199.00, '服饰鞋帽',
             '耐克红色运动鞋，42码，几乎全新，适合跑步和日常穿着，舒适透气',
             None, '2025-01-16 14:20:00', 2),
            ('大学物理教材', 50.00, '学习资料',
             '《大学物理》第五版，上下册全套，有少量笔记，保存完好',
             None, '2025-01-17 09:15:00', 2),
            ('蓝色保温杯', 25.00, '生活用品',
             '膳魔师蓝色保温杯，500ml容量，保温效果好，九成新',
             None, '2025-01-18 16:45:00', 2),
            ('二手智能手机', 1500.00, '电子设备',
             'iPhone X 64GB，黑色，屏幕完好，电池健康度85%，带原装充电器',
             None, '2025-01-19 11:30:00', 2),
            ('无线蓝牙耳机', 120.00, '电子设备',
             '小米AirDots无线蓝牙耳机，音质清晰，续航能力强，九成新',
             None, '2025-01-20 13:10:00', 3),
            ('考研英语词汇书', 30.00, '学习资料',
             '《考研英语词汇》红宝书，全新未使用，带配套APP',
             None, '2025-01-21 15:45:00', 3),
            ('双肩背包', 80.00, '生活用品',
             'Jansport双肩背包，黑色，容量大，适合上课使用',
             None, '2025-01-22 10:20:00', 2),
            ('计算器', 45.00, '学习资料',
             '卡西欧科学计算器，支持多种函数计算，考试必备',
             None, '2025-01-23 14:30:00', 3),
            ('瑜伽垫', 60.00, '生活用品',
             'TPE材质瑜伽垫，防滑加厚，适合室内锻炼',
             None, '2025-01-24 16:15:00', 2)
        ]

        for good in example_goods:
            c.execute('''INSERT INTO goods 
                         (title, price, category, description, image, publish_time, user_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''', good)

        print(f"插入了 {len(example_goods)} 条示例商品数据")

    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成！")


# 4. 搜索相关辅助函数
def normalize_search_query(query):
    """标准化搜索查询，清理特殊字符"""
    if not query:
        return ""

    # 去除首尾空白
    query = query.strip()

    # 过滤掉大部分特殊字符，但保留中文字符、字母、数字和空格
    query = re.sub(r'[^\w\s\u4e00-\u9fff\-\.]', '', query)

    return query


def split_search_keywords(query):
    """将搜索查询拆分为关键词列表"""
    if not query:
        return []

    # 分割关键词（支持中英文空格、逗号、分号分隔）
    keywords = re.split(r'[\s,;]+', query)

    # 过滤掉空字符串
    keywords = [k.strip() for k in keywords if k.strip()]

    return keywords


def generate_goods_description(title, category, price, base_description=""):
    """调用GLM-4-Flash生成/扩写商品描述（新增base_description参数）"""
    # 校验API密钥
    if not GLM_API_KEY or GLM_API_KEY == "monster":
        return "请先配置GLM_API_KEY后再使用AI帮写功能"

    # 构建提示词（核心：区分「全新生成」和「扩写」逻辑）
    if base_description:
        # 有基础描述：执行扩写逻辑
        prompt = f"""
        请你作为校园二手交易平台的用户，基于以下信息对商品描述进行**客观扩写**：
        商品标题：{title}
        商品分类：{category if category else '未指定'}
        商品价格：{price if price else '未指定'}元
        基础描述：{base_description}

        扩写要求：
        1. 完全基于已有信息，不添加虚假/夸大内容，保持客观真实
        2. 补充合理的细节（如使用时长、新旧程度、功能状态、适用场景等），但需标注为「推测」（如“推测使用约1年”）
        3. 语言简洁友好，符合校园二手场景，字数控制在80-150字
        4. 突出商品的实际状态，不使用“极好”“完美”等极端词汇，用“九成新”“功能正常”等客观表述
        5. 保留原描述的核心信息，仅做补充，不修改原意
        """
    else:
        # 无基础描述：全新生成（兼容原有逻辑）
        prompt = f"""
        请你作为校园二手交易平台的用户，为以下商品生成一段客观的二手商品描述：
        商品标题：{title}
        商品分类：{category if category else '未指定'}
        商品价格：{price if price else '未指定'}元

        生成要求：
        1. 语言简洁友好，符合校园二手交易场景
        2. 客观描述商品可能的状态（如使用时长、新旧程度、适用场景），不夸大
        3. 字数控制在50-100字
        4. 语气亲切，符合学生群体的表达习惯
        5. 不使用夸张或虚假的描述，用“推测”“约”等客观词汇
        """

    # 构建请求参数（其余代码不变）
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,  # 降低随机性，保证客观
        "max_tokens": 500
    }

    try:
        # 调用GLM API（其余代码不变）
        response = requests.post(GLM_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get("choices") and len(result["choices"]) > 0:
            description = result["choices"][0]["message"]["content"].strip()
            return description
        else:
            return "AI帮写失败：未获取到有效内容"

    except requests.exceptions.Timeout:
        return "AI帮写失败：请求超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        return f"AI帮写失败：{str(e)}"
    except Exception as e:
        return f"AI帮写异常：{str(e)}"


# ====================== 新增：AI帮写接口 ======================
# 5. 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录！', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/ai/generate_description', methods=['POST'])
@login_required
def ai_generate_description():
    """AI生成/扩写商品描述接口"""
    try:
        # 获取前端参数（新增base_description）
        title = request.json.get('title', '').strip()
        category = request.json.get('category', '').strip()
        price = request.json.get('price', '').strip()
        base_description = request.json.get('base_description', '').strip()  # 新增

        # 参数校验：仅标题必填
        if not title:
            return jsonify({"success": False, "message": "商品标题不能为空"}), 400

        # 价格可选，若有则校验格式
        if price and not price.replace('.', '').isdigit():
            return jsonify({"success": False, "message": "请输入有效的价格"}), 400

        # 调用AI生成/扩写描述（传递base_description参数）
        description = generate_goods_description(title, category, price, base_description)

        return jsonify({
            "success": True,
            "description": description
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"生成失败：{str(e)}"
        }), 500





# 6. 管理员权限验证装饰器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_type' not in session or session['user_type'] != 'admin':
            flash('需要管理员权限！', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


# 7. 用户登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('用户名和密码不能为空！', 'danger')
            return redirect(url_for('login'))

        conn = sqlite3.connect('secondhand.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 查询用户
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()

        if user and user['password'] == password:  # 实际应用中建议使用bcrypt哈希密码
            # 更新最后登录时间
            c.execute('UPDATE users SET last_login = ? WHERE id = ?',
                      (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id']))
            conn.commit()

            # 设置session
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_type'] = user['user_type']

            conn.close()

            flash(f'欢迎回来，{username}！', 'success')

            # 根据用户类型跳转到不同页面
            if user['user_type'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            conn.close()
            flash('用户名或密码错误！', 'danger')
            return redirect(url_for('login'))

    # GET请求：显示登录页面
    return render_template('login.html')


# 8. 用户注册路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        email = request.form.get('email', '').strip()

        # 验证输入
        if not username or not password:
            flash('用户名和密码不能为空！', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('两次输入的密码不一致！', 'danger')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('密码长度至少为6位！', 'warning')
            return redirect(url_for('register'))

        conn = sqlite3.connect('secondhand.db')
        c = conn.cursor()

        # 检查用户名是否已存在
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone():
            conn.close()
            flash('用户名已存在！', 'danger')
            return redirect(url_for('register'))

        # 插入新用户
        try:
            register_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''INSERT INTO users (username, password, email, user_type, register_time)
                         VALUES (?, ?, ?, ?, ?)''',
                      (username, password, email, 'normal', register_time))
            conn.commit()

            # 获取新用户ID并自动登录
            user_id = c.lastrowid
            session['user_id'] = user_id
            session['username'] = username
            session['user_type'] = 'normal'

            conn.close()

            flash('注册成功！欢迎使用校园二手交易平台！', 'success')
            return redirect(url_for('user_dashboard'))

        except Exception as e:
            conn.close()
            flash(f'注册失败：{str(e)}', 'danger')
            return redirect(url_for('register'))

    # GET请求：显示注册页面
    return render_template('register.html')


# 9. 用户仪表板
@app.route('/user/dashboard')
@login_required
def user_dashboard():
    conn = sqlite3.connect('secondhand.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 获取用户信息
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()

    # 获取用户发布的商品
    c.execute('SELECT * FROM goods WHERE user_id = ? ORDER BY publish_time DESC', (session['user_id'],))
    user_goods = c.fetchall()

    conn.close()

    return render_template('user_dashboard.html', user=user, goods=user_goods)


# 10. 管理员仪表板
@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    conn = sqlite3.connect('secondhand.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 获取统计数据
    c.execute('SELECT COUNT(*) as total FROM users')
    user_count = c.fetchone()['total']

    c.execute('SELECT COUNT(*) as total FROM goods')
    goods_count = c.fetchone()['total']

    # 获取所有用户
    c.execute('SELECT * FROM users ORDER BY register_time DESC')
    all_users = c.fetchall()

    # 获取所有商品（关联用户名）
    c.execute('''SELECT goods.*, users.username 
                 FROM goods 
                 LEFT JOIN users ON goods.user_id = users.id 
                 ORDER BY goods.publish_time DESC''')
    all_goods = c.fetchall()

    conn.close()

    return render_template('admin_dashboard.html',
                           user_count=user_count,
                           goods_count=goods_count,
                           users=all_users,
                           goods=all_goods)


# 11. 退出登录
@app.route('/logout')
def logout():
    session.clear()
    flash('您已成功退出登录！', 'success')
    return redirect(url_for('index'))


# 12. 发布商品路由（修复图片路径）
@app.route('/publish', methods=['GET', 'POST'])
@login_required
def publish():
    if request.method == 'POST':
        # 获取表单数据并清洗
        title = request.form.get('title', '').strip()
        price = request.form.get('price', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        file = request.files.get('image')

        # 基础表单验证
        if not title:
            flash('商品标题不能为空！', 'danger')
            return redirect(url_for('publish'))

        if not price or not price.replace('.', '').isdigit():
            flash('请输入有效的价格！', 'danger')
            return redirect(url_for('publish'))

        if not category:
            flash('请选择商品分类！', 'danger')
            return redirect(url_for('publish'))

        # 处理图片上传
        image_filename = None  # 初始化为None，表示使用默认图片
        if file and file.filename != '':
            if allowed_file(file.filename):
                # 生成唯一文件名（避免重复）
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                # 确保上传目录存在
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

                # 保存文件
                try:
                    file.save(upload_path)
                    image_filename = filename  # 只存储文件名
                except Exception as e:
                    flash(f'图片保存失败：{str(e)}', 'danger')
                    # 保存失败时使用默认图片
                    image_filename = None
            else:
                flash('不支持的图片格式！仅支持png/jpg/jpeg/gif', 'warning')
                # 使用默认图片
                image_filename = None

        # 保存商品到数据库
        try:
            publish_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = sqlite3.connect('secondhand.db')
            c = conn.cursor()
            c.execute('''INSERT INTO goods 
                         (title, price, category, description, image, publish_time, user_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (title, float(price), category, description, image_filename, publish_time, session['user_id']))
            conn.commit()
            conn.close()

            flash('商品发布成功！', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'发布失败：{str(e)}', 'danger')
            return redirect(url_for('publish'))

    # GET请求：显示发布页面
    return render_template('publish.html')


# 13. 首页路由
@app.route('/')
def index():
    conn = sqlite3.connect('secondhand.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT goods.*, users.username 
                 FROM goods 
                 LEFT JOIN users ON goods.user_id = users.id 
                 ORDER BY goods.publish_time DESC LIMIT 20''')
    goods = c.fetchall()
    conn.close()

    # 检查用户登录状态
    is_logged_in = 'user_id' in session
    username = session.get('username', '')
    user_type = session.get('user_type', '')

    return render_template('index.html',
                           goods=goods,
                           is_logged_in=is_logged_in,
                           username=username,
                           user_type=user_type)


# 14. 商品详情页路由（修复图片路径获取）
@app.route('/detail/<int:goods_id>')
def detail(goods_id):
    conn = sqlite3.connect('secondhand.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT goods.*, users.username 
                 FROM goods 
                 LEFT JOIN users ON goods.user_id = users.id 
                 WHERE goods.id = ?''', (goods_id,))
    good = c.fetchone()
    conn.close()

    if not good:
        flash('该商品不存在或已下架！', 'danger')
        return redirect(url_for('index'))

    # 处理图片路径
    if good['image']:
        # 如果有自定义图片，构建完整路径
        image_path = f"uploads/{good['image']}"
    else:
        # 使用默认图片
        image_path = "images/default.png"

    # 创建修改后的商品字典
    good_with_image = dict(good)
    good_with_image['image_path'] = image_path

    is_logged_in = 'user_id' in session
    username = session.get('username', '')
    user_type = session.get('user_type', '')

    return render_template('detail.html',
                           good=good_with_image,  # 传递修改后的商品数据
                           is_logged_in=is_logged_in,
                           username=username,
                           user_type=user_type)


# 15. 商品搜索接口
@app.route('/search', methods=['GET'])
def search_goods():
    """搜索商品接口"""
    query = request.args.get('q', '').strip()

    if not query:
        # 如果没有查询词，返回最近发布的商品
        conn = sqlite3.connect('secondhand.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT goods.*, users.username 
            FROM goods 
            LEFT JOIN users ON goods.user_id = users.id 
            ORDER BY goods.publish_time DESC 
            LIMIT 50
        ''')
        results = c.fetchall()
        conn.close()

        return jsonify({
            'success': True,
            'query': '',
            'results': [dict(row) for row in results],
            'count': len(results)
        })

    # 清理查询词
    normalized_query = normalize_search_query(query)
    keywords = split_search_keywords(normalized_query)

    conn = sqlite3.connect('secondhand.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if keywords:
        # 构建多个LIKE条件的查询
        conditions = []
        params = []

        for keyword in keywords:
            conditions.append('(goods.title LIKE ? OR goods.description LIKE ?)')
            params.append(f'%{keyword}%')
            params.append(f'%{keyword}%')

        sql_conditions = ' OR '.join(conditions)

        sql = f'''
            SELECT goods.*, users.username 
            FROM goods 
            LEFT JOIN users ON goods.user_id = users.id 
            WHERE {sql_conditions}
            ORDER BY 
                CASE 
                    WHEN goods.title LIKE ? THEN 1
                    WHEN goods.description LIKE ? THEN 2
                    ELSE 3
                END,
                goods.publish_time DESC
            LIMIT 100
        '''

        # 添加排序参数
        params.append(f'%{keywords[0]}%')
        params.append(f'%{keywords[0]}%')

        c.execute(sql, params)
    else:
        # 如果关键词为空，搜索整个查询词
        sql = '''
            SELECT goods.*, users.username 
            FROM goods 
            LEFT JOIN users ON goods.user_id = users.id 
            WHERE goods.title LIKE ? OR goods.description LIKE ?
            ORDER BY 
                CASE 
                    WHEN goods.title LIKE ? THEN 1
                    WHEN goods.description LIKE ? THEN 2
                    ELSE 3
                END,
                goods.publish_time DESC
            LIMIT 100
        '''
        search_param = f'%{normalized_query}%'
        c.execute(sql, [search_param, search_param, search_param, search_param])

    results = c.fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'query': query,
        'results': [dict(row) for row in results],
        'count': len(results)
    })


# 16. 搜索页面路由
@app.route('/search_page')
def search_page():
    """搜索页面"""
    query = request.args.get('q', '').strip()

    is_logged_in = 'user_id' in session
    username = session.get('username', '')
    user_type = session.get('user_type', '')

    return render_template('search.html',
                           query=query,
                           is_logged_in=is_logged_in,
                           username=username,
                           user_type=user_type)


# 17. 管理员删除商品功能
@app.route('/admin/delete_goods/<int:goods_id>')
@login_required
@admin_required
def delete_goods(goods_id):
    conn = sqlite3.connect('secondhand.db')
    c = conn.cursor()

    # 先获取图片路径，删除图片文件（排除默认图片）
    c.execute('SELECT image FROM goods WHERE id = ?', (goods_id,))
    result = c.fetchone()

    if result and result[0] and result[0] != app.config['DEFAULT_IMAGE']:
        image_path = result[0]
        full_path = os.path.join(app.root_path, image_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                flash(f'图片删除失败：{str(e)}', 'warning')

    # 删除商品记录
    c.execute('DELETE FROM goods WHERE id = ?', (goods_id,))
    conn.commit()
    conn.close()

    flash('商品删除成功！', 'success')
    return redirect(url_for('admin_dashboard'))


# 18. 管理员删除用户功能
@app.route('/admin/delete_user/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    # 不能删除自己
    if user_id == session['user_id']:
        flash('不能删除当前登录的用户！', 'danger')
        return redirect(url_for('admin_dashboard'))

    conn = sqlite3.connect('secondhand.db')
    c = conn.cursor()

    # 先删除用户的所有商品及其图片（排除默认图片）
    c.execute('SELECT image FROM goods WHERE user_id = ?', (user_id,))
    goods_images = c.fetchall()

    for img_record in goods_images:
        if img_record[0] and img_record[0] != app.config['DEFAULT_IMAGE']:
            full_path = os.path.join(app.root_path, img_record[0])
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception as e:
                    flash(f'图片 {img_record[0]} 删除失败：{str(e)}', 'warning')

    # 删除用户的商品
    c.execute('DELETE FROM goods WHERE user_id = ?', (user_id,))

    # 删除用户
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))

    conn.commit()
    conn.close()

    flash('用户删除成功！', 'success')
    return redirect(url_for('admin_dashboard'))


# 19. 用户删除自己的商品
@app.route('/user/delete_my_goods/<int:goods_id>')
@login_required
def delete_my_goods(goods_id):
    conn = sqlite3.connect('secondhand.db')
    c = conn.cursor()

    # 验证商品是否属于当前用户
    c.execute('SELECT image, user_id FROM goods WHERE id = ?', (goods_id,))
    result = c.fetchone()

    if not result:
        conn.close()
        flash('商品不存在！', 'danger')
        return redirect(url_for('user_dashboard'))

    if result[1] != session['user_id']:
        conn.close()
        flash('只能删除自己发布的商品！', 'danger')
        return redirect(url_for('user_dashboard'))

    # 删除图片文件（排除默认图片）
    if result[0] and result[0] != app.config['DEFAULT_IMAGE']:
        full_path = os.path.join(app.root_path, result[0])
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                flash(f'图片删除失败：{str(e)}', 'warning')

    # 删除商品记录
    c.execute('DELETE FROM goods WHERE id = ?', (goods_id,))
    conn.commit()
    conn.close()

    flash('商品删除成功！', 'success')
    return redirect(url_for('user_dashboard'))

# AI智搜
@app.route('/ai_search', methods=['POST'])
@login_required
def ai_search():
    """AI智能搜索：解析自然语言查询，提取条件后搜索商品"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'message': '查询不能为空'}), 400

        # 调用GLM解析查询
        parsed = parse_query_with_glm(query)
        if not parsed:
            # 解析失败，回退到普通关键词搜索
            return jsonify({'success': False, 'message': 'AI解析失败，请尝试普通搜索'}), 500

        # 构建SQL查询
        conn = sqlite3.connect('secondhand.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        sql = '''
            SELECT goods.*, users.username 
            FROM goods 
            LEFT JOIN users ON goods.user_id = users.id 
            WHERE 1=1
        '''
        params = []

        # 分类条件
        if parsed.get('category'):
            sql += ' AND category = ?'
            params.append(parsed['category'])

        # 价格范围
        if parsed.get('price_min') is not None:
            sql += ' AND price >= ?'
            params.append(parsed['price_min'])
        if parsed.get('price_max') is not None:
            sql += ' AND price <= ?'
            params.append(parsed['price_max'])

        # 关键词条件（标题或描述包含任意关键词）
        keywords = parsed.get('keywords', [])
        if keywords:
            keyword_conditions = []
            for kw in keywords:
                keyword_conditions.append('(title LIKE ? OR description LIKE ?)')
                params.append(f'%{kw}%')
                params.append(f'%{kw}%')
            sql += ' AND (' + ' OR '.join(keyword_conditions) + ')'

        sql += ' ORDER BY publish_time DESC LIMIT 50'

        c.execute(sql, params)
        results = c.fetchall()
        conn.close()

        return jsonify({
            'success': True,
            'query': query,
            'results': [dict(row) for row in results],
            'count': len(results)
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'AI搜索出错：{str(e)}'}), 500


def parse_query_with_glm(query):
    """调用GLM解析用户查询，返回结构化字典"""
    prompt = f"""
你是一个智能商品搜索助手，请分析用户的搜索查询，提取关键信息，并以JSON格式输出。
用户查询：{query}

要求输出JSON包含以下字段：
- keywords: 列表，用于搜索标题和描述的关键词（可包含同义词、相关词），至少包含原始查询中的核心词。
- category: 字符串，如果查询中提到了商品分类，则提取；否则为null。分类必须是以下之一：学习资料、电子设备、生活用品、服饰鞋帽、其他物品。如果提到的商品不属于这些，则为null。
- price_min: 数字或null，如果查询中提到了最低价格，例如“100元以上”则min=100；否则null。
- price_max: 数字或null，如果查询中提到了最高价格，例如“不超过2000元”则max=2000；否则null。

注意：
- 价格范围只提取明确的数字，不要猜测。
- 关键词列表应包含查询中的所有重要词汇，并可能添加同义词以扩大搜索。

输出示例：
{{"keywords": ["手机", "智能手机"], "category": "电子设备", "price_min": null, "price_max": 1500}}
只输出JSON，不要其他解释。
"""
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500
    }
    try:
        response = requests.post(GLM_API_URL, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content'].strip()
        # 提取JSON部分（防止模型输出额外内容）
        import json
        # 查找第一个{和最后一个}
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end > start:
            json_str = content[start:end]
            parsed = json.loads(json_str)
            # 确保字段存在
            return {
                'keywords': parsed.get('keywords', []),
                'category': parsed.get('category'),
                'price_min': parsed.get('price_min'),
                'price_max': parsed.get('price_max')
            }
        else:
            return None
    except Exception as e:
        print(f"GLM解析失败: {e}")
        return None

#
# 20. 程序入口
if __name__ == '__main__':
    # 初始化数据库
    init_db()

    # 检查默认图片是否存在，不存在则创建空文件（或替换为实际默认图片路径）
    if not os.path.exists(app.config['DEFAULT_IMAGE']):
        try:
            os.makedirs(os.path.dirname(app.config['DEFAULT_IMAGE']), exist_ok=True)
            # 创建一个简单的默认图片（实际项目中可以放一个真正的图片）
            with open(app.config['DEFAULT_IMAGE'], 'wb') as f:
                # 这里可以放一个真实的图片，但现在先创建空文件
                pass
        except Exception as e:
            print(f"创建默认图片失败: {e}")

    print("=" * 60)
    print("校园二手交易平台启动成功！")
    print("访问地址: http://localhost:8080")
    print("测试账户:")
    print("  管理员: admin / admin123")
    print("  普通用户: user1 / user123")
    print("=" * 60)

    # 启动Flask服务
    app.run(host='0.0.0.0', port=8080, debug=True)