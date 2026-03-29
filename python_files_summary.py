#!/usr/bin/env python3
import os
import glob

def count_python_files():
    """统计当前目录及其子目录中的所有Python文件"""
    python_files = []
    
    # 使用glob递归搜索所有.py文件
    for file_path in glob.glob("**/*.py", recursive=True):
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    line_count = len(lines)
                    # 统计空行和注释行
                    empty_lines = 0
                    comment_lines = 0
                    for line in lines:
                        stripped = line.strip()
                        if not stripped:
                            empty_lines += 1
                        elif stripped.startswith('#'):
                            comment_lines += 1
                    
                    python_files.append({
                        'path': file_path,
                        'lines': line_count,
                        'empty_lines': empty_lines,
                        'comment_lines': comment_lines,
                        'code_lines': line_count - empty_lines - comment_lines
                    })
            except Exception as e:
                print(f"无法读取文件 {file_path}: {e}")
    
    return python_files

def print_summary(files):
    """打印统计摘要"""
    print("=" * 80)
    print("Python文件搜索统计报告")
    print("=" * 80)
    print(f"\n找到的Python文件总数: {len(files)}")
    
    if not files:
        return
    
    # 按目录分组
    dir_groups = {}
    for file_info in files:
        dir_path = os.path.dirname(file_info['path'])
        if dir_path == '':
            dir_path = '.'
        if dir_path not in dir_groups:
            dir_groups[dir_path] = []
        dir_groups[dir_path].append(file_info)
    
    # 打印按目录分组的统计
    print("\n按目录分组:")
    print("-" * 80)
    for dir_path in sorted(dir_groups.keys()):
        dir_files = dir_groups[dir_path]
        total_lines = sum(f['lines'] for f in dir_files)
        total_code = sum(f['code_lines'] for f in dir_files)
        print(f"{dir_path}/: {len(dir_files)} 个文件, {total_lines} 行, {total_code} 行代码")
    
    # 总体统计
    total_lines = sum(f['lines'] for f in files)
    total_empty = sum(f['empty_lines'] for f in files)
    total_comments = sum(f['comment_lines'] for f in files)
    total_code = sum(f['code_lines'] for f in files)
    
    print("\n总体统计:")
    print("-" * 80)
    print(f"总行数: {total_lines}")
    print(f"代码行数: {total_code} ({total_code/total_lines*100:.1f}%)")
    print(f"注释行数: {total_comments} ({total_comments/total_lines*100:.1f}%)")
    print(f"空行数: {total_empty} ({total_empty/total_lines*100:.1f}%)")
    
    # 文件大小分布
    print("\n文件大小分布:")
    print("-" * 80)
    small = [f for f in files if f['lines'] < 50]
    medium = [f for f in files if 50 <= f['lines'] < 200]
    large = [f for f in files if f['lines'] >= 200]
    
    print(f"小型文件 (<50行): {len(small)} 个")
    print(f"中型文件 (50-200行): {len(medium)} 个")
    print(f"大型文件 (≥200行): {len(large)} 个")
    
    # 最大的5个文件
    print("\n最大的5个Python文件:")
    print("-" * 80)
    sorted_files = sorted(files, key=lambda x: x['lines'], reverse=True)
    for i, file_info in enumerate(sorted_files[:5], 1):
        print(f"{i}. {file_info['path']}: {file_info['lines']} 行 "
              f"(代码: {file_info['code_lines']}, 注释: {file_info['comment_lines']}, 空行: {file_info['empty_lines']})")
    
    # 完整的文件列表
    print("\n完整的Python文件列表:")
    print("-" * 80)
    for i, file_info in enumerate(sorted(files, key=lambda x: x['path']), 1):
        print(f"{i:2d}. {file_info['path']} ({file_info['lines']} 行)")

if __name__ == "__main__":
    files = count_python_files()
    print_summary(files)