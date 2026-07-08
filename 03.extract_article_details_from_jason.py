import json
import csv
import re
from collections import defaultdict

def extract_doi_from_journal(journal_text):
    """
    从journal字段中精确提取doi:和下一个"之间的内容
    格式示例："...doi:10.xxxx/xxxx",...
    """
    if not journal_text:
        return ""
    
    # 匹配doi:后面直到下一个"的内容
    match = re.search(r'doi:\s*([^"]+)', journal_text)
    if match:
        doi = match.group(1).strip()
        # 去除可能存在的结尾标点
        doi = re.sub(r'[.,;]$', '', doi)
        return doi
    return ""

def extract_pubtator_data(json_file, output_file):
    """
    从PubTator格式的JSON文件中提取结构化数据并保存为TSV
    
    参数:
        json_file: 输入的JSON文件路径
        output_file: 输出的TSV文件路径
    """
    # 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = []
    
    # 遍历每个batch
    for batch_key, batch_data in data.items():
        # 检查是否是PubTator3数据
        if 'PubTator3' not in batch_data:
            continue
            
        # 遍历每个条目
        for entry in batch_data['PubTator3']:
            # 基础信息
            pmid = str(entry.get('pmid', ''))
            authors = ', '.join(entry.get('authors', []))
            
            # 初始化结果字典
            record = {
                'PMID': pmid,
                'Journal': '',
                'Year': '',
                'DOI': '',
                'PMCID': '',
                'Authors': authors,
                'Title': '',
                'Abstract': '',
                'Gene_IDs': '',
                'Gene_Names': '',
                'Gene_Databases': '',
                'Species': '',
                'Species_IDs': '',
                'Species_Databases': '',
                'Chemicals': '',
                'Chemical_IDs': '',
                'Chemical_Databases': '',
                'Diseases': '',
                'Disease_IDs': '',
                'Disease_Databases': '',
                'Relations_Display': ''
            }
            
            # 首先从条目顶层提取PMCID和日期
            record['PMCID'] = entry.get('pmcid', '')
            date_str = entry.get('date', '')
            if date_str:
                year_match = re.search(r'(\d{4})', date_str)
                if year_match:
                    record['Year'] = year_match.group(1)
            
            # 处理relations_display
            relations_display = []
            for rel in entry.get('relations_display', []):
                if 'name' in rel:
                    relations_display.append(rel['name'])
            if relations_display:
                record['Relations_Display'] = '; '.join(relations_display)
            
            # 从passages中提取信息
            for passage in entry.get('passages', []):
                infons = passage.get('infons', {})
                text = passage.get('text', '')
                
                # 取journal信息（优先从infons中获取）
                journal = infons.get('journal', '')
                if journal:
                    record['Journal'] = journal
                    # 从journal字段提取DOI
                    record['DOI'] = extract_doi_from_journal(journal)
                
                # 提取标题
                if infons.get('type') == 'title':
                    record['Title'] = text
                
                # 提取摘要
                elif infons.get('type') == 'abstract':
                    record['Abstract'] = text
                
                # 从infons中提取PMCID（优先级高于顶层）
                if 'article-id_pmc' in infons:
                    record['PMCID'] = infons['article-id_pmc']
                
                # 如果没有从顶层获取到年份，尝试从journal中提取
                if not record['Year'] and journal:
                    year_match = re.search(r'(\d{4})', journal)
                    if year_match:
                        record['Year'] = year_match.group(1)
                
                # 处理annotations
                species = []
                species_ids = []
                species_dbs = []
                
                genes = defaultdict(list)
                gene_dbs = []
                
                chemicals = []
                chemical_ids = []
                chemical_dbs = []
                
                diseases = []
                disease_ids = []
                disease_dbs = []
                
                for annotation in passage.get('annotations', []):
                    a_infons = annotation.get('infons', {})
                    a_type = a_infons.get('type', '')
                    a_text = annotation.get('text', '')
                    a_id = a_infons.get('identifier', '')
                    a_db = a_infons.get('database', '')
                    
                    if a_type == 'Species':
                        species.append(a_text)
                        species_ids.append(a_id)
                        species_dbs.append(a_db)
                    elif a_type == 'Gene':
                        gene_id = a_infons.get('identifier', '')
                        if gene_id:
                            genes['id'].append(gene_id)
                            genes['name'].append(a_text)
                            gene_dbs.append(a_db)
                    elif a_type == 'Chemical':
                        chem_name = a_infons.get('name', a_text)
                        chemicals.append(chem_name)
                        chemical_ids.append(a_id)
                        chemical_dbs.append(a_db)
                    elif a_type == 'Disease':
                        disease_name = a_infons.get('name', a_text)
                        diseases.append(disease_name)
                        disease_ids.append(a_id)
                        disease_dbs.append(a_db)
                
                # 合并信息
                if species:
                    record['Species'] = '|'.join(species)
                    record['Species_IDs'] = '|'.join(species_ids)
                    record['Species_Databases'] = '|'.join(species_dbs)
                
                if genes['id']:
                    record['Gene_IDs'] = '|'.join(genes['id'])
                    record['Gene_Names'] = '|'.join(genes['name'])
                    record['Gene_Databases'] = '|'.join(gene_dbs)
                
                if chemicals:
                    record['Chemicals'] = '|'.join(chemicals)
                    record['Chemical_IDs'] = '|'.join(chemical_ids)
                    record['Chemical_Databases'] = '|'.join(chemical_dbs)
                
                if diseases:
                    record['Diseases'] = '|'.join(diseases)
                    record['Disease_IDs'] = '|'.join(disease_ids)
                    record['Disease_Databases'] = '|'.join(disease_dbs)
            
            results.append(record)
    
    # 写入TSV文件
    if results:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys(), delimiter='\t')
            writer.writeheader()
            writer.writerows(results)
        print(f"成功提取 {len(results)} 条录到 {output_file}")
    else:
        print("未提取到有效数据")

# 使用示例
if __name__ == '__main__':
    input_json = 'raw_api_responses.json'
    output_tsv = 'extracted_articles.tsv'
    extract_pubtator_data(input_json, output_tsv)
