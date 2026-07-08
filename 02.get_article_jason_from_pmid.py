import requests
import json
import time
from typing import List, Dict, Any
import os

# ===== 配置参数 =====
PUBTATOR_API_URL = "https://www.ncbi.nlm.nih.gov/research/pubtator-api/publications/export/biocjson"
REQUEST_DELAY = 0.5  # 每次请求的延迟(秒)
BATCH_SIZE = 10      # 每次请求的PMID数量
INPUT_PMID_FILE = "pmid_list.txt"  # 确保此文件存在且包含有效PMID
RAW_DATA_FILE = "raw_api_responses.json"
DEBUG_RAW_DATA = True

def read_pmids_from_file(file_path: str) -> List[str]:
    """读取PMID列表"""
    print(f"尝试从文件读取PMID: {file_path}")  # 调试日志
    if not os.path.exists(file_path):
        print(f"错误: 文件 {file_path} 不存在!")  # 错误日志
        exit(1)
    
    pmid_list = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                pmid = line.strip()
                if pmid:
                    if not pmid.isdigit():
                        print(f"警告: 跳过无效PMID '{pmid}' (必须为数)")  # 警告日志
                        continue
                    pmid_list.append(pmid)
        print(f"成功读取 {len(pmid_list)} 个有效PMID")  # 调试日志
        return pmid_list
    except Exception as e:
        print(f"读取PMID文错误: {str(e)}")  # 错误日志
        exit(1)

def fetch_pubtator_data_batch(pmid_batch: List[str]) -> List[Any]:
    """批量获取PubTator API数据"""
    params = {"pmids": ",".join(pmid_batch)}  # 将PMID列表用逗号连接
    print(f"\n正在请求 {len(pmid_batch)} 个PMID的数据...")  # 调试日志
    try:
        response = requests.get(PUBTATOR_API_URL, params=params, timeout=10)
        print(f"API响应状态码: {response.status_code}")  # 调试日志
        
        if response.status_code != 200:
            print(f"错误: 批量请求失败，状态码: {response.status_code}")  # 错误日志
            return []
            
        data = response.json()
        print(f"成功获取 {len(pmid_batch)} 个PMID的数据")  # 调试日志
        return data
    except requests.exceptions.RequestException as e:
        print(f"批量获取PMID数据失败: {str(e)}")  # 错误日志
        return []

def process_pmids(pmid_list: List[str]):
    """处理所有PMID，仅保原始API响应"""
    print(f"\n开始处理 {len(pmid_list)} 个PMID...")  # 调试日志
    raw_data = {}
    
    # 将PMID列表分成批次
    for i in range(0, len(pmid_list), BATCH_SIZE):
        batch = pmid_list[i:i + BATCH_SIZE]
        print(f"\n正在处理批次 {i//BATCH_SIZE + 1}: PMIDs {batch[0]} 到 {batch[-1]}")  # 调试日志
        
        data = fetch_pubtator_data_batch(batch)
        if isinstance(data, list):
            # 假设API返回的是列表，且顺序与batch一致
            if len(data) == len(batch):
                for pmid, item in zip(batch, data):
                    raw_data[pmid] = item
            else:
                print(f"警告: 批量响应数据长度({len(data)})与请求PMID数量({len(batch)})匹配")
                # 将整个响应存储为特殊键
                raw_data[f"batch_{i//BATCH_SIZE}"] = data
        else:
            # 如果不是列表，可能是其他结构，直接存储
            raw_data[f"batch_{i//BATCH_SIZE}"] = data
        
        time.sleep(REQUEST_DELAY)
        print(f"已完成批次 {i//BATCH_SIZE + 1} 的处理")  # 调试日志
    
    if DEBUG_RAW_DATA:
        with open(RAW_DATA_FILE, "w") as f:
            json.dump(raw_data, f, indent=2)
        print(f"\nRaw API responses saved to '{RAW_DATA_FILE}'")  # 成功日志
    
    print(f"已完成所有 {len(pmid_list)} 个PMID的处理")  # 完成日志

def main():
    print("="*50)  # 分隔线
    print("PubTator批量数据提取工具")  # 更新标题
    print("="*50)  # 分隔线
    
    start_time = time.time()
    print(f"脚本启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")  # 时间日志
    
    pmid_list = read_pmids_from_file(INPUT_PMID_FILE)
    if not pmid_list:
        print("错: 没有有效的PMID可处理!")  # 错误日志
        return
        
    print(f"准备处理 {len(pmid_list)} 个PMID...")  # 调试日志
    process_pmids(pmid_list)
    
    end_time = time.time()
    elapsed = end_time - start_time
    print(f"\n脚本运行完成，总耗时: {elapsed:.2f}秒")  # 完成日志

if __name__ == "__main__":
    main()
