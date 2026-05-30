"""Generate expanded golden_cases.json (80+) from existing 39 cases."""
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
EXISTING = FIXTURES / "golden_cases.json"
OUTPUT = FIXTURES / "golden_cases_expanded.json"

with open(EXISTING, encoding="utf-8") as f:
    data = json.load(f)

existing_names = {c["full_name"] for c in data["cases"]}

# ── New cases (41 additions → 80 total) ─────────────────────────────────

new_cases = [
    # ═══ TOP5: Daily picks — browser automation, AI agents, RAG ═══
    {
        "full_name": "ItzCrazyKns/Perplexica",
        "name": "Perplexica",
        "description": "AI-powered search engine built with Next.js and search APIs. Perplexica is an open source AI search tool.",
        "topics": ["ai-search", "seo", "geo", "search-engine", "nextjs", "llm", "rag"],
        "stars": 25000, "forks": 3000, "language": "TypeScript", "license": "MIT",
        "contributors_count": 25,
        "readme": "## Perplexica — AI Search Engine\n\nAn AI-powered search engine.\n\n### Installation\nnpm install\n\n### Demo\nLive demo at perplexica.example.com\n\n### Features\n- AI search with multiple sources\n- GEO optimization\n- Self-hostable",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "medium",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
            "platform_fit_ranges": {"geo_trade": {"min": 75, "max": 100}}
        },
    },
    {
        "full_name": "BerriAI/litellm",
        "name": "litellm",
        "description": "Call all LLM APIs using the OpenAI format. Use Bedrock, Azure, OpenAI, Cohere, Anthropic, Ollama, Sagemaker, HuggingFace, Replicate.",
        "topics": ["llm", "api", "openai", "proxy", "gateway", "anthropic", "ai"],
        "stars": 20000, "forks": 2500, "language": "Python", "license": "MIT",
        "contributors_count": 60,
        "readme": "## LiteLLM — Universal LLM Proxy\n\nCall 100+ LLMs with OpenAI format.\n\n### Quick Start\npip install litellm\n\n### Enterprise Features\n- Load balancing\n- Rate limiting\n- Cost tracking\n- Virtual keys\n\n### Demo\nTry our playground at demo.litellm.ai",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 85, "max": 100},
            "platform_fit_ranges": {"videohao": {"min": 70, "max": 100}, "wechat": {"min": 70, "max": 100}}
        },
    },
    {
        "full_name": "OpenInterpreter/open-interpreter",
        "name": "open-interpreter",
        "description": "A natural language interface for computers. Let LLMs run code on your computer to complete tasks.",
        "topics": ["ai", "llm", "agent", "code-interpreter", "automation", "python"],
        "stars": 58000, "forks": 5000, "language": "Python", "license": "AGPL-3.0",
        "contributors_count": 40,
        "readme": "## Open Interpreter\n\nNatural language interface for computers.\n\n### Installation\npip install open-interpreter\n\n### Quick Start\n```python\ninterpreter.chat('Plot AAPL stock')\n```\n\n### Demo\n![demo](demo.gif)\n\n### Use Cases\n- Data analysis\n- File operations\n- Web scraping\n- System automation",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "medium",
            "repo_selection_score": {"min": 80, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
            "platform_fit_ranges": {"douyin": {"min": 70, "max": 100}}
        },
    },
    {
        "full_name": "chatchat-space/Langchain-Chatchat",
        "name": "Langchain-Chatchat",
        "description": "基于Langchain和ChatGLM的本地知识库问答系统，支持中文企业级RAG应用。",
        "topics": ["rag", "langchain", "chatglm", "knowledge-base", "llm", "chinese", "ai"],
        "stars": 32000, "forks": 5000, "language": "Python", "license": "Apache-2.0",
        "contributors_count": 15,
        "readme": "## Langchain-Chatchat\n\n基于 Langchain 和 ChatGLM 的本地知识库问答系统。\n\n### 功能\n- 企业知识库问答\n- 中文文档理解\n- 多种LLM支持\n- 私有化部署\n\n### 安装\n```bash\ndocker-compose up -d\n```\n\n### Demo\n在线体验: demo.example.com\n\n### 应用场景\n- 企业内部知识管理\n- 客服系统\n- 文档智能问答",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 85, "max": 100},
            "platform_fit_ranges": {"wechat": {"min": 75, "max": 100}, "videohao": {"min": 75, "max": 100}}
        },
    },
    {
        "full_name": "continuedev/continue",
        "name": "continue",
        "description": "Open-source AI code assistant. Connect any models and any context to build custom autocomplete and chat experiences inside your IDE.",
        "topics": ["ai", "llm", "code-assistant", "ide", "autocomplete", "developer-tools"],
        "stars": 25000, "forks": 2000, "language": "TypeScript", "license": "Apache-2.0",
        "contributors_count": 100,
        "readme": "## Continue — AI Code Assistant\n\nOpen-source AI code assistant for your IDE.\n\n### Installation\nInstall from VS Code marketplace.\n\n### Quick Start\nConnect your favorite LLM (OpenAI, Anthropic, Ollama, etc.)\n\n### Features\n- Tab autocomplete\n- Chat with codebase\n- Custom slash commands\n- Multi-model support\n\n### Demo\n![demo](demo.gif)",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
        },
    },
    {
        "full_name": "geekan/MetaGPT",
        "name": "MetaGPT",
        "description": "Multi-agent framework that assigns different roles to GPTs to form a collaborative software company.",
        "topics": ["ai", "agent", "multi-agent", "gpt", "software-development", "automation"],
        "stars": 48000, "forks": 5000, "language": "Python", "license": "MIT",
        "contributors_count": 50,
        "readme": "## MetaGPT — Multi-Agent Framework\n\nAssign different roles to GPTs to form a collaborative entity.\n\n### Installation\npip install metagpt\n\n### Quick Start\nmetagpt \"Write a snake game\"\n\n### Architecture\n- Product Manager agent\n- Architect agent\n- Engineer agent\n- QA agent\n\n### Demo\n![demo](demo.png)\n\n### Enterprise Use\n- Software prototyping\n- Requirement analysis\n- Code generation",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "medium",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
        },
    },
    {
        "full_name": "danielmiessler/fabric",
        "name": "fabric",
        "description": "fabric is an open-source framework for augmenting humans using AI. It provides a modular framework for solving specific problems using a crowdsourced set of AI prompts.",
        "topics": ["ai", "prompt-engineering", "llm", "automation", "cli", "agent"],
        "stars": 30000, "forks": 3000, "language": "Go", "license": "MIT",
        "contributors_count": 30,
        "readme": "## Fabric — AI Augmentation Framework\n\nModular framework for augmenting humans using AI.\n\n### Installation\n```bash\ngo install github.com/danielmiessler/fabric@latest\n```\n\n### Quick Start\nfabric --pattern summarize_paper\n\n### Patterns\n- summarization\n- analysis\n- extraction\n- creation\n\n### Demo\n![demo](demo.gif)",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
        },
    },
    {
        "full_name": "CopilotKit/CopilotKit",
        "name": "CopilotKit",
        "description": "React UI + infrastructure for AI copilots. Build in-app AI chatbots, AI agents, AI textareas, and more.",
        "topics": ["ai", "copilot", "react", "chatbot", "agent", "llm", "ui"],
        "stars": 15000, "forks": 1500, "language": "TypeScript", "license": "MIT",
        "contributors_count": 25,
        "readme": "## CopilotKit\n\nReact UI for AI copilots.\n\n### Installation\nnpm install @copilotkit/react-core\n\n### Quick Start\n```tsx\n<CopilotKit>\n  <YourApp />\n</CopilotKit>\n```\n\n### Demo\n![demo](demo.gif)\n\n### Enterprise\n- Custom AI copilots\n- In-app assistants\n- AI textareas",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 70, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
        },
    },
    {
        "full_name": "BuilderIO/gpt-crawler",
        "name": "gpt-crawler",
        "description": "Crawl a site to generate knowledge files to create your own custom GPT or RAG application.",
        "topics": ["ai", "crawler", "gpt", "rag", "scraper", "knowledge-base"],
        "stars": 20000, "forks": 2000, "language": "TypeScript", "license": "MIT",
        "contributors_count": 10,
        "readme": "## GPT Crawler\n\nCrawl websites to generate knowledge files for GPT/RAG.\n\n### Installation\nnpm install\n\n### Quick Start\nConfigure your target URL and run the crawler.\n\n### Use Cases\n- Build custom GPTs\n- RAG knowledge bases\n- Web to JSON for AI\n\n### Demo\n![demo](demo.gif)",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "medium",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 75, "max": 100},
            "platform_fit_ranges": {"geo_trade": {"min": 65, "max": 100}}
        },
    },
    {
        "full_name": "stanford-oval/storm",
        "name": "storm",
        "description": "An LLM-powered knowledge curation system that researches a topic and generates a full-length report with citations.",
        "topics": ["ai", "llm", "research", "rag", "agent", "knowledge"],
        "stars": 18000, "forks": 1500, "language": "Python", "license": "MIT",
        "contributors_count": 12,
        "readme": "## STORM — AI Research System\n\nLLM-powered knowledge curation and report generation.\n\n### Installation\npip install knowledge-storm\n\n### Quick Start\n```python\nfrom knowledge_storm import StormRunner\n```\n\n### Demo\nSee generated reports at storm.example.com\n\n### Use Cases\n- Automated research\n- Report generation\n- Literature review",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 75, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
        },
    },
    {
        "full_name": "katanaml/sparrow",
        "name": "sparrow",
        "description": "Data extraction with ML and LLM. Parse documents, invoices, receipts into structured JSON.",
        "topics": ["ai", "llm", "data-extraction", "ocr", "document-ai", "rag"],
        "stars": 8000, "forks": 800, "language": "Python", "license": "Apache-2.0",
        "contributors_count": 8,
        "readme": "## Sparrow — Document AI\n\nData extraction with ML and LLM.\n\n### Installation\npip install sparrow-ml\n\n### Quick Start\nExtract data from PDFs, images, and documents.\n\n### Use Cases\n- Invoice parsing\n- Receipt extraction\n- Document understanding\n\n### Demo\n![demo](demo.png)",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 70, "max": 100},
            "business_value_score": {"min": 75, "max": 100},
        },
    },
    {
        "full_name": "vanna-ai/vanna",
        "name": "vanna",
        "description": "AI-powered business intelligence. Ask questions to your database in natural language and get answers with charts.",
        "topics": ["ai", "sql", "business-intelligence", "llm", "rag", "data"],
        "stars": 12000, "forks": 1000, "language": "Python", "license": "MIT",
        "contributors_count": 15,
        "readme": "## Vanna — AI Business Intelligence\n\nAsk questions in natural language, get SQL and charts.\n\n### Installation\npip install vanna\n\n### Quick Start\n```python\nvn.ask('What were our top 5 products last month?')\n```\n\n### Enterprise\n- Database-agnostic\n- Self-hosted\n- Custom training\n\n### Demo\n![demo](demo.gif)",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 70, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
            "platform_fit_ranges": {"videohao": {"min": 70, "max": 100}}
        },
    },
    {
        "full_name": "activepieces/activepieces",
        "name": "activepieces",
        "description": "Open source no-code business automation. Alternative to Zapier. Automate workflows with AI.",
        "topics": ["automation", "workflow", "no-code", "ai", "business", "open-source"],
        "stars": 16000, "forks": 1800, "language": "TypeScript", "license": "MIT",
        "contributors_count": 40,
        "readme": "## Activepieces — No-Code Automation\n\nOpen source alternative to Zapier with AI capabilities.\n\n### Installation\n```bash\ndocker-compose up -d\n```\n\n### Demo\nTry at demo.activepieces.com\n\n### Features\n- AI-powered automation\n- Visual workflow builder\n- Webhook triggers\n- 200+ integrations\n\n### Enterprise\n- Self-hosted\n- SSO\n- Audit logs",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 70, "max": 100},
            "business_value_score": {"min": 80, "max": 100},
            "platform_fit_ranges": {"videohao": {"min": 75, "max": 100}}
        },
    },

    # ═══ EVERGREEN: Big frameworks, infrastructure, platforms ═══
    {
        "full_name": "FlowiseAI/Flowise",
        "name": "Flowise",
        "description": "Drag & drop UI to build your customized LLM flow. Build AI apps with visual low-code builder.",
        "topics": ["llm", "ai", "low-code", "langchain", "visual-builder", "workflow"],
        "stars": 35000, "forks": 4000, "language": "TypeScript", "license": "Apache-2.0",
        "contributors_count": 40,
        "readme": "## Flowise — Low-Code LLM Apps\n\nDrag & drop UI to build LLM flows.\n\n### Installation\nnpm install -g flowise\n\n### Quick Start\nflowise start\n\n### Features\n- Visual builder\n- LangChain integration\n- API endpoints\n\n### Demo\n![demo](demo.png)",
        "expected": {
            "pool": "top5", "content_type": "runnable_project", "risk_overall": "low",
            "repo_selection_score": {"min": 70, "max": 100},
            "business_value_score": {"min": 75, "max": 100},
        },
    },
    {
        "full_name": "ggerganov/llama.cpp",
        "name": "llama.cpp",
        "description": "LLM inference in C/C++. Run Llama, Mistral, and other models locally on CPU.",
        "topics": ["llm", "cpp", "inference", "ai", "machine-learning", "quantization"],
        "stars": 75000, "forks": 10000, "language": "C++", "license": "MIT",
        "contributors_count": 200,
        "readme": "## llama.cpp — LLM Inference in C/C++\n\nRun LLMs locally on CPU.\n\n### Installation\n```bash\nmake\n```\n\n### Quick Start\n./llama-cli -m model.gguf -p \"Hello\"\n\n### Features\n- Quantization\n- GPU acceleration\n- Server mode\n\n### Architecture\nSupports GGUF format with optimized inference kernels.",
        "expected": {
            "pool": "evergreen", "content_type": "framework_tool", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
            "business_value_score": {"min": 70, "max": 100},
        },
    },
    {
        "full_name": "huggingface/transformers",
        "name": "transformers",
        "description": "Transformers: State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.",
        "topics": ["machine-learning", "nlp", "deep-learning", "pytorch", "tensorflow", "ai"],
        "stars": 140000, "forks": 28000, "language": "Python", "license": "Apache-2.0",
        "contributors_count": 500,
        "readme": "## Transformers\n\nState-of-the-art Machine Learning for PyTorch, TensorFlow, and JAX.\n\n### Installation\npip install transformers\n\n### Quick Start\n```python\nfrom transformers import pipeline\nclassifier = pipeline('sentiment-analysis')\n```\n\n### Architecture\nPre-trained models for NLP, vision, audio.\n\n### Models\nBERT, GPT, T5, Llama, and thousands more.",
        "expected": {
            "pool": "evergreen", "content_type": "framework_tool", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
            "business_value_score": {"min": 70, "max": 100},
        },
    },
    {
        "full_name": "apache/airflow",
        "name": "airflow",
        "description": "Apache Airflow - A platform to programmatically author, schedule, and monitor workflows.",
        "topics": ["workflow", "automation", "scheduler", "python", "data-engineering", "pipeline"],
        "stars": 40000, "forks": 16000, "language": "Python", "license": "Apache-2.0",
        "contributors_count": 400,
        "readme": "## Apache Airflow\n\nProgrammatically author, schedule, and monitor workflows.\n\n### Installation\npip install apache-airflow\n\n### Quick Start\nairflow standalone\n\n### Architecture\n- DAG-based workflow definition\n- Scheduler\n- Web UI\n- Executors\n\n### Enterprise\n- Kubernetes executor\n- Multi-tenant\n- RBAC",
        "expected": {
            "pool": "evergreen", "content_type": "framework_tool", "risk_overall": "medium",
            "repo_selection_score": {"min": 50, "max": 100},
            "business_value_score": {"min": 70, "max": 100},
        },
    },
    {
        "full_name": "PrefectHQ/prefect",
        "name": "prefect",
        "description": "Prefect is a workflow orchestration framework for building resilient data pipelines in Python.",
        "topics": ["workflow", "automation", "orchestration", "python", "data", "pipeline"],
        "stars": 19000, "forks": 1800, "language": "Python", "license": "Apache-2.0",
        "contributors_count": 100,
        "readme": "## Prefect\n\nWorkflow orchestration for data pipelines.\n\n### Installation\npip install prefect\n\n### Quick Start\n```python\nfrom prefect import flow, task\n```\n\n### Architecture\n- Task-based flows\n- Cloud orchestration\n- Retry and error handling\n\n### Enterprise\n- Prefect Cloud\n- Self-hosted server\n- RBAC",
        "expected": {
            "pool": "evergreen", "content_type": "framework_tool", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
            "business_value_score": {"min": 70, "max": 100},
        },
    },
    {
        "full_name": "milvus-io/milvus",
        "name": "milvus",
        "description": "Milvus is a high-performance, cloud-native vector database built for scalable similarity search and AI applications.",
        "topics": ["vector-database", "similarity-search", "ai", "embeddings", "rag", "database"],
        "stars": 33000, "forks": 3000, "language": "Go", "license": "Apache-2.0",
        "contributors_count": 70,
        "readme": "## Milvus — Vector Database\n\nCloud-native vector database for AI.\n\n### Installation\ndocker-compose up -d\n\n### Quick Start\n```python\nfrom pymilvus import Collection\n```\n\n### Architecture\n- Distributed\n- GPU-accelerated\n- Multiple index types\n\n### Enterprise\n- Cloud-native\n- Kubernetes\n- Multi-replica",
        "expected": {
            "pool": "evergreen", "content_type": "framework_tool", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
            "business_value_score": {"min": 70, "max": 100},
        },
    },
    {
        "full_name": "deepset-ai/haystack",
        "name": "haystack",
        "description": "Haystack is an open source NLP framework to build LLM applications with an orchestration pipeline.",
        "topics": ["nlp", "rag", "llm", "search", "question-answering", "ai"],
        "stars": 20000, "forks": 2000, "language": "Python", "license": "Apache-2.0",
        "contributors_count": 45,
        "readme": "## Haystack — NLP Framework\n\nBuild production-ready LLM applications.\n\n### Installation\npip install haystack-ai\n\n### Quick Start\n```python\nfrom haystack import Pipeline\n```\n\n### Architecture\n- Component-based pipeline\n- RAG pipelines\n- Agent pipelines\n\n### Enterprise\n- Self-hosted\n- API endpoints\n- Custom components",
        "expected": {
            "pool": "evergreen", "content_type": "framework_tool", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
            "business_value_score": {"min": 75, "max": 100},
        },
    },

    # ═══ RESOURCE: Awesome lists, prompt collections, tutorials ═══
    {
        "full_name": "f/awesome-chatgpt-prompts",
        "name": "awesome-chatgpt-prompts",
        "description": "A collection of prompt examples to be used with the ChatGPT model. Curated prompts for various use cases.",
        "topics": ["chatgpt", "prompts", "awesome-list", "ai", "gpt"],
        "stars": 120000, "forks": 16000, "language": "HTML", "license": "CC0-1.0",
        "contributors_count": 50,
        "readme": "## Awesome ChatGPT Prompts\n\nA collection of prompt examples.\n\n### Prompts\n- Act as a Linux Terminal\n- Act as an English Translator\n- ...\n\nThis is a curated list of prompts for ChatGPT.",
        "expected": {
            "pool": "resource", "content_type": "awesome_list", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
        },
    },
    {
        "full_name": "e2b-dev/awesome-ai-agents",
        "name": "awesome-ai-agents",
        "description": "A list of AI autonomous agents. Curated collection of agents, frameworks, and tools.",
        "topics": ["awesome-list", "ai-agents", "ai", "agent"],
        "stars": 15000, "forks": 1500, "language": "Markdown", "license": "MIT",
        "contributors_count": 15,
        "readme": "## Awesome AI Agents\n\nA curated list of AI autonomous agents.\n\n### Categories\n- Frameworks\n- Tools\n- Research\n\n### Agents Listed\nAutoGPT, BabyAGI, CrewAI, and more...",
        "expected": {
            "pool": "resource", "content_type": "awesome_list", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
        },
    },
    {
        "full_name": "dair-ai/Prompt-Engineering-Guide",
        "name": "Prompt-Engineering-Guide",
        "description": "Guides, papers, lecture, notebooks and resources for prompt engineering in LLMs.",
        "topics": ["prompt-engineering", "llm", "guide", "tutorial", "ai"],
        "stars": 55000, "forks": 5000, "language": "Jupyter Notebook", "license": "MIT",
        "contributors_count": 20,
        "readme": "## Prompt Engineering Guide\n\nResources for prompt engineering.\n\n### Contents\n- Introduction to Prompt Engineering\n- Techniques\n- Applications\n- Papers\n\n### Guides\nZero-shot, few-shot, chain-of-thought, and more.",
        "expected": {
            "pool": "resource", "content_type": "tutorial_guide", "risk_overall": "low",
            "repo_selection_score": {"min": 50, "max": 100},
        },
    },
    {
        "full_name": "ouckah/awesome-ai-agents",
        "name": "awesome-ai-agents",
        "description": "A curated list of awesome AI agents and agentic tools. Frameworks, platforms, and research.",
        "topics": ["awesome-list", "ai", "agent", "llm", "collection"],
        "stars": 5000, "forks": 500, "language": "Markdown", "license": "",
        "contributors_count": 3,
        "readme": "## Awesome AI Agents\n\nCurated list of AI agents.\n\n### Frameworks\n- LangChain\n- CrewAI\n- AutoGPT\n\n### Tools\n- browser-use\n- Composio\n- ...",
        "expected": {
            "pool": "resource", "content_type": "awesome_list", "risk_overall": "low",
            "repo_selection_score": {"min": 40, "max": 100},
        },
    },
    {
        "full_name": "ai-collection/ai-collection",
        "name": "ai-collection",
        "description": "A collection of awesome generative AI applications. Directory of AI tools and apps.",
        "topics": ["awesome-list", "ai", "generative-ai", "collection", "tools"],
        "stars": 8000, "forks": 800, "language": "TypeScript", "license": "MIT",
        "contributors_count": 15,
        "readme": "## AI Collection\n\nDirectory of generative AI applications.\n\n### Categories\n- Chat\n- Image Generation\n- Video\n- Audio\n- Code\n\n### Apps Listed\nChatGPT, Midjourney, Stable Diffusion, and hundreds more.",
        "expected": {
            "pool": "resource", "content_type": "awesome_list", "risk_overall": "low",
            "repo_selection_score": {"min": 40, "max": 100},
        },
    },
    {
        "full_name": "EbookFoundation/free-programming-books",
        "name": "free-programming-books",
        "description": "Freely available programming books. A massive collection of learning resources.",
        "topics": ["books", "education", "programming", "learning", "resource"],
        "stars": 350000, "forks": 62000, "language": "HTML", "license": "CC-BY-4.0",
        "contributors_count": 150,
        "readme": "## Free Programming Books\n\nFreely available programming books.\n\n### Languages\n- Python\n- JavaScript\n- Java\n- C++\n\n### Subjects\n- Algorithms\n- Machine Learning\n- ...",
        "expected": {
            "pool": "resource", "content_type": "awesome_list", "risk_overall": "low",
            "repo_selection_score": {"min": 30, "max": 100},
        },
    },
    {
        "full_name": "papers-we-love/papers-we-love",
        "name": "papers-we-love",
        "description": "Papers from the computer science community to read and discuss. Academic paper collection.",
        "topics": ["papers", "computer-science", "reading", "research", "academic"],
        "stars": 92000, "forks": 6000, "language": "Shell", "license": "",
        "contributors_count": 80,
        "readme": "## Papers We Love\n\nAcademic papers from the CS community.\n\n### Topics\n- Machine Learning\n- Systems\n- Programming Languages\n- ...\n\n### How to Use\nRead, discuss, present.",
        "expected": {
            "pool": "resource", "content_type": "awesome_list", "risk_overall": "low",
            "repo_selection_score": {"min": 30, "max": 100},
        },
    },

    # ═══ BLOCKED: High-risk/deepfake/phishing/malware ═══
    {
        "full_name": "iperov/DeepFaceLab",
        "name": "DeepFaceLab",
        "description": "DeepFaceLab is the leading software for creating deepfakes. Face swapping tool for videos.",
        "topics": ["deepfake", "face-swap", "machine-learning", "computer-vision"],
        "stars": 50000, "forks": 11000, "language": "Python", "license": "GPL-3.0",
        "contributors_count": 5,
        "readme": "## DeepFaceLab — Deepfake Creation\n\nLeading software for creating deepfakes.\n\n### Installation\nFollow setup guide.\n\n### Usage\nSwap faces in videos with deep learning.\n\n### Warning\nThis software can be used to create deceptive content.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "s0md3v/roop",
        "name": "roop",
        "description": "One-click deepfake (face swap). Take a video and replace the face with just one image.",
        "topics": ["deepfake", "face-swap", "ai", "computer-vision"],
        "stars": 29000, "forks": 6000, "language": "Python", "license": "GPL-3.0",
        "contributors_count": 3,
        "readme": "## Roop — One-Click Deepfake\n\nReplace faces in videos with one click.\n\n### Installation\npip install roop\n\n### Usage\nSelect video and target face image. Click run.\n\n### Warning\nBe responsible. Face swapping without consent is illegal in many jurisdictions.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "CorentinJ/Real-Time-Voice-Cloning",
        "name": "Real-Time-Voice-Cloning",
        "description": "Clone a voice in 5 seconds to generate arbitrary speech in real-time. Voice deepfake tool.",
        "topics": ["voice-cloning", "deep-learning", "audio", "speech", "deepfake"],
        "stars": 54000, "forks": 9000, "language": "Python", "license": "MIT",
        "contributors_count": 3,
        "readme": "## Real-Time Voice Cloning\n\nClone a voice in 5 seconds.\n\n### Installation\npip install -r requirements.txt\n\n### Usage\nRecord 5 seconds of voice, generate arbitrary speech.\n\n### Warning\nVoice cloning can be used for impersonation and fraud.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "soxv/BlackEye-Phishing",
        "name": "BlackEye-Phishing",
        "description": "Ultimate phishing tool with 38 websites templates. Social engineering toolkit.",
        "topics": ["phishing", "security", "social-engineering", "hacking"],
        "stars": 3000, "forks": 1000, "language": "HTML", "license": "",
        "contributors_count": 2,
        "readme": "## BlackEye — Phishing Toolkit\n\n38 website templates for phishing campaigns.\n\n### Usage\nCreate convincing fake login pages.\n\n### Warning\nPhishing is illegal. This tool is for educational purposes only.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "trustedsec/social-engineer-toolkit",
        "name": "social-engineer-toolkit",
        "description": "The Social-Engineer Toolkit (SET) — penetration testing framework for social engineering attacks.",
        "topics": ["security", "social-engineering", "penetration-testing", "phishing"],
        "stars": 11000, "forks": 2500, "language": "Python", "license": "BSD-3-Clause",
        "contributors_count": 10,
        "readme": "## Social-Engineer Toolkit\n\nPenetration testing framework for social engineering.\n\n### Features\n- Spear phishing\n- Website attack vectors\n- Mass mailer\n\n### Usage\nFor authorized penetration testing only.\n\n### Warning\nUnauthorized use is illegal.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "secretscanner/credential-dumper",
        "name": "credential-dumper",
        "description": "Search and dump credentials from browser stores — Chrome, Firefox, Edge. Password recovery tool.",
        "topics": ["security", "password", "credential", "recovery"],
        "stars": 1500, "forks": 300, "language": "Python", "license": "",
        "contributors_count": 1,
        "readme": "## Credential Dumper\n\nExtract saved passwords from browsers.\n\n### Supported Browsers\n- Chrome\n- Firefox\n- Edge\n\n### Usage\nFor recovering YOUR OWN passwords only.\n\n### Warning\nUsing this on others' computers is illegal.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "TheSpeedX/SMS-Bomber",
        "name": "SMS-Bomber",
        "description": "SMS and email bomber. Send bulk messages for testing or harassment.",
        "topics": ["sms", "spam", "bomber", "tool"],
        "stars": 2000, "forks": 500, "language": "Python", "license": "",
        "contributors_count": 1,
        "readme": "## SMS Bomber\n\nSend bulk SMS messages.\n\n### Usage\npython bomber.py --target NUMBER --count 100\n\n### Warning\nSMS bombing is illegal. For educational use only.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
    {
        "full_name": "fake-author/spam-bot-net",
        "name": "spam-bot-net",
        "description": "Automated bot network for social media spam. Generate accounts and post spam content.",
        "topics": ["spam", "bot", "automation", "social-media"],
        "stars": 1000, "forks": 200, "language": "JavaScript", "license": "",
        "contributors_count": 1,
        "readme": "## Spam Bot Network\n\nAutomated social media spam.\n\n### Features\n- Account generation\n- Auto-posting\n- Proxy support\n- Captcha bypass\n\n### Warning\nSpam operations violate platform ToS.",
        "expected": {
            "pool": "blocked", "content_type": "high_risk", "risk_overall": "blocked",
            "repo_selection_score": {"min": 0, "max": 100},
        },
    },
]

# ── Validate no duplicates ──
for c in new_cases:
    if c["full_name"] in existing_names:
        print(f"DUPLICATE: {c['full_name']}")

# ── Merge ──
data["cases"].extend(new_cases)
data["version"] = "2.0.0"
data["description"] = "扩展黄金样本集 — 80+ 典型 GitHub AI 项目，覆盖 5 大类型 + 8 blocked cases，用于 Phase 6 评分校准。"
data["total"] = len(data["cases"])

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Written {len(data['cases'])} cases to {OUTPUT}")

# Pool breakdown
pools = {}
for c in data["cases"]:
    p = c["expected"]["pool"]
    pools[p] = pools.get(p, 0) + 1
print(f"Pools: {pools}")
