import json
import time
from datetime import datetime
from pathlib import Path
from Bio import Entrez

# ================== 配置参数 ==================
Entrez.email = "lv18298436282@gmail.com"  # 必须替换为有效邮箱
batch_size = 5000        # 可以增大批次，因为只获取ID
max_retries = 3          # 网络请求最大重试次数
request_delay = 0.5      # 可以缩短延迟，因为请求更简单
output_dir = Path("./pubmed_pmids")  # 输出目录
search_term_file = Path("keywords.txt")  # 搜索词文件路径

# 年份范围
current_year = datetime.now().year
years = list(range(1979, current_year + 1))

# 初始化输出目录和进度文件
output_dir.mkdir(exist_ok=True)
progress_file = output_dir / "progress.json"

# ================== 新增合并函数 ==================
def merge_pmid_files():
    """合并所有年份的PMID文件并添加总数统计"""
    merged_file = output_dir / "../pmid_list.txt"  # 修改合并文件名为pmid_list.txt
    all_pmids = []
    
    # 集所有年份的PMID
    for year_file in output_dir.glob("pmids_*.txt"):
        with open(year_file, "r") as f:
            pmids = f.read().splitlines()
            all_pmids.extend(pmids)
    
    # 去重并统计总数
    unique_pmids = list(set(all_pmids))
    total_count = len(unique_pmids)
    
    # 写入合并文件
    with open(merged_file, "w") as f:
        f.write(f"# Total unique PMIDs: {total_count}\n")
        f.write(f"# Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n".join(unique_pmids))
    
    print(f"\n合并完成！共找到 {total_count} 个唯一PMID，已保存到 {merged_file}")

# ================== 工具函数 ==================
def load_search_terms():
    """从txt文件加载搜索词"""
    if not search_term_file.exists():
        raise FileNotFoundError(f"搜索词文件 {search_term_file} 不存在")
    
    with open(search_term_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    # 验证搜索词有效性
    if not content or len(content) < 5:
        raise ValueError("搜索词内容过短或无效")
    
    return content

def load_progress():
    """加载进度信息"""
    if progress_file.exists():
        with open(progress_file, "r") as f:
            return json.load(f)
    return {"completed": [], "failed": {}, "last_run": datetime.now().isoformat()}

def save_progress(progress):
    """保存进度信息"""
    progress["last_run"] = datetime.now().isoformat()
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)

def save_pmids(pmids, year):
    """保存PMID到文本文件"""
    if not pmids:
        print(f"{year} 年无相关文献")
        return
    
    filename = output_dir / f"pmids_{year}.txt"
    try:
        with open(filename, "w") as f:
            f.write("\n".join(pmids))
        print(f"成功保存 {len(pmids)} 个PMID到 {filename}")
    except Exception as e:
        print(f"文件保存失败: {str(e)}")
        raise

# ================== 核心逻辑 ==================
def fetch_year_pmids(year, progress, search_term):
    """获取指定年份的所有PMID"""
    if str(year) in progress["completed"]:
        print(f"跳过已完成的年份: {year}")
        return []
    
    print(f"\n{'='*30}\n开始处理 {year} 年")
    query = f'({search_term}) AND ("{year}"[Date - Publication])'
    
    # 获取总记录数
    total = 0
    for attempt in range(max_retries):
        try:
            with Entrez.esearch(db="pubmed", term=query, retmax=0) as handle:
                search_data = Entrez.read(handle)
                total = int(search_data["Count"])
                print(f"发现 {total} 篇相关文献")
                break
        except Exception as e:
            print(f"总查询失败（尝试 {attempt+1}/{max_retries}）: {str(e)}")
            time.sleep(request_delay * 2)
    else:
        print(f"无法获取 {year} 年数据总数")
        progress["failed"][str(year)] = "总数查询失败"
        return []

    # 分页取所有PMID
    all_pmids = []
    for offset in range(0, total, batch_size):
        print(f"获取PMID {offset+1}-{min(offset+batch_size, total)}...")
        
        for attempt in range(max_retries):
            try:
                with Entrez.esearch(
                    db="pubmed",
                    term=query,
                    retstart=offset,
                    retmax=batch_size,
                    rettype="uilist"  # 只返回ID列表
                ) as handle:
                    id_list = Entrez.read(handle)["IdList"]
                
                all_pmids.extend(id_list)
                time.sleep(request_delay)
                break
            except Exception as e:
                print(f"获取失败（尝试 {attempt+1}/{max_retries}）: {str(e)}")
                if attempt == max_retries - 1:
                    print(f"{year} 年PMID获取不完整（位置 {offset}）")
                    progress["failed"][str(year)] = f"中断于 {offset}"
                    return all_pmids
                time.sleep(request_delay * 2)

    # 标记该年份为已完成
    progress["completed"].append(str(year))
    return all_pmids

# ================== 主程序 ==================
def main():
    """主控制流程"""
    try:
        search_term = load_search_terms()
        print("加载的搜索词:\n", search_term)
    except Exception as e:
        print(f"加载搜索词失败: {str(e)}")
        return
    
    progress = load_progress()
    print(f"加载进度：完成 {len(progress['completed'])} 年，失败 {len(progress['failed'])} 年")
    
    try:
        for year in years:
            if str(year) in progress["completed"]:
                continue
            
            pmids = fetch_year_pmids(year, progress, search_term)
            if pmids:
                save_pmids(pmids, year)
            
            save_progress(progress)
            time.sleep(request_delay)
        
        # 所有年份完成后自动合并文件
        merge_pmid_files()
            
    except KeyboardInterrupt:
        print("\n用户中断，保存进度...")
    finally:
        save_progress(progress)
        print("\n最终进度：")
        print(json.dumps(progress, indent=2))

if __name__ == "__main__":
    start_time = time.time()
    time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== 程序启动于 {time_str} ===")
    
    main()
    
    duration = time.time() - start_time
    print(f"=== 运行完成，耗时 {duration:.2f} 秒 ===")
