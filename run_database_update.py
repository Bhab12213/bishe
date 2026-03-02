[file name]: run_database_update.py
[file content begin]
#!/usr/bin/env python3
"""
校园二手交易平台 - 数据库升级工具
用于添加用户登录功能到现有数据库
"""

import sqlite3
import os
import sys
import shutil
from datetime import datetime

def backup_database(db_file='secondhand.db', backup_dir='backups'):
    """备份现有数据库"""
    
    if not os.path.exists(db_file):
        print(f"⚠️  警告：数据库文件 {db_file} 不存在，将创建新数据库")
        return True
    
    # 创建备份目录
    os.makedirs(backup_dir, exist_ok=True)
    
    # 生成带时间戳的备份文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f'secondhand_backup_{timestamp}.db')
    
    try:
        shutil.copy2(db_file, backup_file)
        print(f"✅ 数据库已备份到: {backup_file}")
        
        # 同时复制一份到当前目录作为最近备份
        shutil.copy2(db_file, 'secondhand_backup.db')
        print(f"✅ 同时创建了最近备份: secondhand_backup.db")
        
        return True
    except Exception as e:
        print(f"❌ 备份失败: {e}")
        return False

def check_database_structure(db_file='secondhand.db'):
    """检查当前数据库结构"""
    
    if not os.path.exists(db_file):
        print(f"📁 数据库文件 {db_file} 不存在，将创建新数据库")
        return False
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        print("🔍 当前数据库结构检查:")
        
        # 获取所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if not tables:
            print("   ⚠️  数据库中没有表，需要全新初始化")
            return False
        
        print(f"   发现 {len(tables)} 个表:")
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"     - {table_name} ({len(columns)} 列)")
            for col in columns:
                print(f"        {col[1]} ({col[2]})")
        
        # 检查是否有用户表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        has_users = cursor.fetchone()
        
        # 检查商品表是否有 user_id 列
        cursor.execute("PRAGMA table_info(goods)")
        goods_columns = [col[1] for col in cursor.fetchall()]
        has_user_id = 'user_id' in goods_columns
        
        conn.close()
        
        if has_users and has_user_id:
            print("✅ 用户登录功能已存在")
            return True
        else:
            print("⚠️  需要添加用户登录功能")
            return False
            
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")
        return False

def execute_sql_update(db_file='secondhand.db', sql_file='update_schema.sql'):
    """执行SQL更新脚本"""
    
    # 检查SQL文件是否存在
    if not os.path.exists(sql_file):
        print(f"❌ SQL文件 {sql_file} 不存在！")
        print("请确保 update_schema.sql 文件在同一目录下")
        return False
    
    try:
        # 读取SQL文件
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 连接到数据库
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("🔄 开始执行数据库更新...")
        
        # 分割SQL语句（按分号分割）
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        for i, statement in enumerate(sql_statements, 1):
            if statement:
                try:
                    # 打印简化的语句信息（只显示前100个字符）
                    preview = statement[:100] + "..." if len(statement) > 100 else statement
                    print(f"   [{i}/{len(sql_statements)}] 执行: {preview}")
                    
                    cursor.execute(statement)
                    
                    # 如果是SELECT语句，显示部分结果
                    if statement.strip().upper().startswith('SELECT'):
                        results = cursor.fetchall()
                        if results and len(results) <= 5:  # 只显示少量结果
                            for row in results:
                                print(f"      → {dict(row)}")
                    
                except sqlite3.OperationalError as e:
                    # 忽略一些无害的错误（如列已存在）
                    error_msg = str(e).lower()
                    if any(keyword in error_msg for keyword in ['already exists', 'duplicate column', 'no such table']):
                        print(f"      ⚠️  跳过（预期中）: {e}")
                    else:
                        print(f"      ❌ SQL错误: {e}")
                        # 对于关键错误，询问是否继续
                        if 'DROP TABLE' in statement.upper():
                            print(f"      ⚠️  注意：这是删除表操作，可能需要手动处理")
                except Exception as e:
                    print(f"      ❌ 执行出错: {e}")
        
        # 提交更改
        conn.commit()
        
        # 验证更新结果
        print("\n✅ 数据库更新完成！")
        print("\n🔍 验证更新结果:")
        
        # 检查用户表
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"   用户表：{user_count} 条记录")
        
        # 检查商品表的 user_id 列
        cursor.execute("PRAGMA table_info(goods)")
        columns = cursor.fetchall()
        goods_columns = [col['name'] for col in columns]
        
        if 'user_id' in goods_columns:
            # 统计已分配用户的商品数量
            cursor.execute("SELECT COUNT(*) FROM goods WHERE user_id IS NOT NULL")
            assigned_goods = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM goods")
            total_goods = cursor.fetchone()[0]
            print(f"   商品表：已添加 user_id 列，{assigned_goods}/{total_goods} 商品已分配用户")
        else:
            print(f"   ❌ 商品表未成功添加 user_id 列")
        
        # 显示部分用户数据
        cursor.execute("SELECT id, username, user_type FROM users ORDER BY id LIMIT 5")
        users = cursor.fetchall()
        print(f"   示例用户数据:")
        for user in users:
            print(f"      ID:{user['id']} 用户名:{user['username']} 类型:{user['user_type']}")
        
        # 显示部分商品数据
        cursor.execute("SELECT id, title, user_id FROM goods ORDER BY id LIMIT 5")
        goods = cursor.fetchall()
        print(f"   示例商品数据:")
        for good in goods:
            print(f"      ID:{good['id']} 标题:{good['title'][:20]}... 用户ID:{good['user_id']}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 数据库更新失败: {e}")
        print("💡 提示：您可以尝试手动修复，或使用备份文件恢复数据库")
        return False

def test_user_login(db_file='secondhand.db'):
    """测试用户登录功能"""
    
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("\n🧪 测试用户登录功能...")
        
        # 测试管理员登录
        cursor.execute("SELECT * FROM users WHERE username='admin' AND password='admin123'")
        admin = cursor.fetchone()
        
        if admin:
            print(f"✅ 管理员账户可用：{admin['username']} (ID: {admin['id']})")
        else:
            print("❌ 管理员账户测试失败")
        
        # 测试普通用户登录
        cursor.execute("SELECT * FROM users WHERE username='user1' AND password='user123'")
        user1 = cursor.fetchone()
        
        if user1:
            print(f"✅ 普通用户账户可用：{user1['username']} (ID: {user1['id']})")
        else:
            print("❌ 普通用户账户测试失败")
        
        # 测试商品用户关联
        cursor.execute("""
            SELECT goods.id, goods.title, users.username 
            FROM goods 
            LEFT JOIN users ON goods.user_id = users.id 
            WHERE goods.user_id IS NOT NULL 
            LIMIT 3
        """)
        goods_with_users = cursor.fetchall()
        
        if goods_with_users:
            print("✅ 商品用户关联正常，示例:")
            for good in goods_with_users:
                print(f"   商品『{good['title'][:15]}...』 ← 用户: {good['username']}")
        else:
            print("⚠️  没有找到已关联用户的商品")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 功能测试失败: {e}")
        return False

def main():
    """主函数"""
    
    print("=" * 60)
    print("校园二手交易平台 - 数据库升级工具")
    print("版本: 1.0 (用户登录功能升级)")
    print("=" * 60)
    
    # 检查当前状态
    print("\n📊 系统状态检查:")
    check_database_structure()
    
    # 询问是否备份
    print("\n🔒 数据安全确认:")
    backup_choice = input("是否创建数据库备份？强烈建议备份！(y/n): ").strip().lower()
    
    if backup_choice in ['y', 'yes', '是']:
        backup_database()
    else:
        confirm = input("⚠️  跳过备份可能导致数据丢失！确定继续吗？(输入 'confirm' 继续): ").strip()
        if confirm != 'confirm':
            print("❌ 操作已取消")
            sys.exit(0)
    
    # 询问是否继续更新
    print("\n🚀 准备执行数据库更新:")
    confirm_update = input("确定要执行数据库更新吗？(y/n): ").strip().lower()
    
    if confirm_update not in ['y', 'yes', '是']:
        print("❌ 操作已取消")
        sys.exit(0)
    
    # 执行更新
    print("\n" + "=" * 60)
    success = execute_sql_update()
    
    if success:
        # 测试功能
        test_user_login()
        
        print("\n" + "=" * 60)
        print("🎉 数据库更新完成！")
        print("\n接下来您可以：")
        print("1. 运行 python app.py 启动应用")
        print("2. 使用以下账户测试登录：")
        print("   - 管理员：admin / admin123")
        print("   - 普通用户：user1 / user123")
        print("3. 访问 http://localhost:8080")
        print("=" * 60)
        
        # 询问是否立即启动应用
        launch = input("\n是否立即启动应用？(y/n): ").strip().lower()
        if launch in ['y', 'yes', '是']:
            print("正在启动 Flask 应用...")
            os.system("python app.py")
    else:
        print("\n❌ 更新失败，请检查错误信息")
        print("💡 您可以：")
        print("1. 检查 update_schema.sql 文件是否存在")
        print("2. 使用备份文件恢复数据库")
        print("3. 手动执行SQL语句")

if __name__ == '__main__':
    main()
[file content end]