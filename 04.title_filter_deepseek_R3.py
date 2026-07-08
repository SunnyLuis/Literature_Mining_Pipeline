import os
import csv
import asyncio
import json
from typing import List, Dict, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from datetime import datetime
from openai import AsyncOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class StressStudyClassifier:
    def __init__(self, stress_type: str, config_file: str = "config.json", templates_file: str = "prompt_templates.json"):
        self.stress_type = stress_type
        self.config_file = config_file
        self.templates_file = templates_file
        
        # Load configurations
        self._load_config()
        self._load_templates()
        
        # Set up API client
        api_key = self.config.get("api_key")
        if not api_key:
            env_var_name = self.config.get("api_key_env", "DEEPSEEK_API_KEY")
            api_key = os.environ.get(env_var_name)
            
        if not api_key:
            raise ValueError(f"API key not found. Please set it in config.json or environment variables.")
            
        self.client = AsyncOpenAI(
            base_url=self.config.get("base_url", "https://api.deepseek.com/v1"),
            api_key=api_key
        )
        
        self.model_name = self.config.get("model_name", "deepseek-chat")
        self.max_tokens = self.config.get("max_tokens", 10)
        self.temperature = self.config.get("temperature", 0.0)
        self.rate_limit_delay = self.config.get("rate_limit_delay_seconds", 0.1)
        self.batch_size = self.config.get("batch_size", 50)
        
        # Set up cache
        self.cache_file = f"{stress_type}_filter_cache.json"
        self.filter_cache = {}
        self._init_cache()
        
        self.last_request_time = None
        self.request_count = 0

    def _load_config(self):
        """Load API and model configurations from external config file"""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load config file: {e}")
            raise

    def _load_templates(self):
        """Load prompt templates from external templates file"""
        try:
            with open(self.templates_file, "r", encoding="utf-8") as f:
                templates = json.load(f)
                self.filter_template = templates["filter_templates"][self.stress_type]
        except Exception as e:
            logging.error(f"Failed to load prompt templates for {self.stress_type}: {e}")
            raise ValueError(f"Prompt template for '{self.stress_type}' not found in {self.templates_file}.")

    def _init_cache(self):
        """Load local cache to prevent redundant API calls"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.filter_cache = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Persist cache data to disk"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.filter_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Failed to save cache: {e}")

    async def _rate_limit_delay(self):
        """Rate limiting to prevent hitting API thresholds"""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = datetime.now()
        self.request_count += 1
        if self.request_count % 100 == 0:
            await asyncio.sleep(1.0)

    @retry(stop=stop_after_attempt(5), 
           wait=wait_exponential(multiplier=1, min=4, max=20),
           reraise=True)
    async def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """Helper to invoke LLM with robustness retries"""
        try:
            await self._rate_limit_delay()
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                ),
                timeout=30
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"API request failed: {e}")
            raise

    async def is_stress_study(self, pmid: str, title: str, abstract: str) -> bool:
        """Classifies if a paper is relevant based on title and abstract"""
        # Return from cache if processed before
        if pmid in self.filter_cache:
            return self.filter_cache[pmid] == "relevant"
        
        # Prepare prompts
        system_prompt = self.filter_template["system_prompt"]
        user_prompt = self.filter_template["user_prompt_template"].format(
            title=title,
            abstract=abstract if abstract.strip() else "No abstract available."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            response = await self._call_api(messages)
            response_clean = response.strip().lower()
            
            # Substring match to handle potential LLM punctuation/prefix variations
            is_relevant = "relevant" in response_clean and "irrelevant" not in response_clean
            
            # Cache the result
            self.filter_cache[pmid] = "relevant" if is_relevant else "irrelevant"
            self._save_cache()
            
            return is_relevant
        except Exception as e:
            logging.warning(f"Classification failed for PMID {pmid}: {e}")
            raise

async def filter_studies(stress_type: str, input_file: str, output_dir: str):
    """Orchestrator to perform batch async classification on the dataset"""
    os.makedirs(output_dir, exist_ok=True)
    classifier = StressStudyClassifier(stress_type)
    
    # Read the input dataset and headers dynamically
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
        
    with open(input_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = reader.fieldnames
        if not fieldnames or "PMID" not in fieldnames or "Title" not in fieldnames:
            raise ValueError("Input file must contain at least 'PMID' and 'Title' columns.")
        articles = [row for row in reader]
    
    print(f"Starting batch classification for '{stress_type}' stress studies...")
    relevant_articles = []
    irrelevant_articles = []
    failed_articles = []

    batch_size = classifier.batch_size
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        
        # Create asynchronous classification tasks
        tasks = [
            classifier.is_stress_study(art["PMID"], art["Title"], art.get("Abstract", ""))
            for art in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for art, result in zip(batch, results):
            if isinstance(result, Exception):
                failed_articles.append(art)
                continue
            if result:
                relevant_articles.append(art)
            else:
                irrelevant_articles.append(art)
                
        print(f"Progress: {min(i+batch_size, len(articles))}/{len(articles)} articles classified.")

    # Helper function to save TSV files preserving original headers
    def save_results(data: List[Dict[str, Any]], filename: str):
        if not data:
            return
        output_path = os.path.join(output_dir, filename)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(data)

    save_results(relevant_articles, f"{stress_type}_relevant.tsv")
    save_results(irrelevant_articles, f"{stress_type}_irrelevant.tsv")

    # Output stats in English
    total = len(articles)
    stats = {
        "Total Articles": total,
        "Relevant Articles": len(relevant_articles),
        "Irrelevant Articles": len(irrelevant_articles),
        "Failed Classifications": len(failed_articles)
    }
    
    print("\n" + "="*40)
    print("Classification Summary Statistics")
    print("="*40)
    for key, val in stats.items():
        percentage = f" ({val/total:.1%})" if total > 0 and key != "Total Articles" else ""
        print(f"{key}: {val}{percentage}")
    print("="*40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Classify plant scientific papers based on title and abstract using DeepSeek-V3.")
    parser.add_argument("--stress", required=True, help="Type of stress to filter (e.g., salt_alkali, drought)")
    parser.add_argument("--input", default="extracted_articles.tsv", help="Path to input TSV file")
    parser.add_argument("--output", default="filtered_results", help="Directory path to save results")
    args = parser.parse_args()
    
    asyncio.run(filter_studies(
        stress_type=args.stress,
        input_file=args.input,
        output_dir=args.output
    ))
