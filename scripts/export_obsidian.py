#!/usr/bin/env python3
"""
HAX-Mind Obsidian Vault Exporter
แปลงองค์ความรู้ทั้งหมดเป็น Obsidian Vault Format
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

def sanitize_filename(name: str) -> str:
    """แปลงชื่อไฟล์ให้ปลอดภัย"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)[:100]

def json_to_markdown(json_path: Path, output_dir: Path) -> Path:
    """แปลง JSON file เป็น Markdown"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        return None
    
    # สร้างชื่อไฟล์ .md
    md_filename = json_path.stem + '.md'
    md_path = output_dir / md_filename
    
    lines = []
    
    # Frontmatter
    lines.append('---')
    if 'id' in data:
        lines.append(f'id: {data["id"]}')
    if 'created_at' in data:
        lines.append(f'created: {data["created_at"]}')
    if 'title' in data:
        lines.append(f'title: {data["title"]}')
    if 'confidence' in data:
        lines.append(f'confidence: {data["confidence"]}')
    lines.append(f'source: {json_path}')
    lines.append('---')
    lines.append('')
    
    # Title
    title = data.get('title', json_path.stem)
    lines.append(f'# {title}')
    lines.append('')
    
    # Summary
    if 'summary' in data:
        lines.append(f'> {data["summary"]}')
        lines.append('')
    
    # Content ตามประเภท
    if 'text' in data:
        lines.append(data['text'])
        lines.append('')
    
    # Evidence (สำหรับ decisions)
    if 'evidence' in data and data['evidence']:
        lines.append('## Evidence')
        for ev in data['evidence']:
            ev_title = ev.get('title', 'Unknown')
            ev_type = ev.get('type', 'note')
            lines.append(f'- [[{sanitize_filename(ev_title)}]] ({ev_type})')
        lines.append('')
    
    # Top Terms
    if 'top_terms' in data and data['top_terms']:
        lines.append('## Keywords')
        lines.append(', '.join([f'`{t}`' for t in data['top_terms'][:10]]))
        lines.append('')
    
    # Metadata
    if 'metadata' in data and data['metadata']:
        lines.append('## Metadata')
        for key, value in data['metadata'].items():
            lines.append(f'- **{key}**: {value}')
        lines.append('')
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    return md_path

def create_moc(vault_dir: Path, title: str, files: list, description: str = '') -> Path:
    """สร้าง Map of Content (MOC)"""
    moc_path = vault_dir / f'📋 {title}.md'
    
    lines = [
        f'# {title}',
        '',
    ]
    
    if description:
        lines.append(description)
        lines.append('')
    
    # สร้างตาราง
    lines.append('| Document | Created | Summary |')
    lines.append('|----------|---------|---------|')
    
    for f in sorted(files):
        # อ่านไฟล์เพื่อหา created date และ title
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                # หา created date
                created_match = re.search(r'created: (.+)', content)
                created = created_match.group(1)[:10] if created_match else '-'
                
                # หา title
                title_match = re.search(r'^# (.+)', content, re.MULTILINE)
                display_title = title_match.group(1) if title_match else f.stem
        except:
            created = '-'
            display_title = f.stem
        
        link_name = f.stem
        lines.append(f'| [[{link_name}|{display_title[:40]}]] | {created} | ... |')
    
    lines.append('')
    lines.append(f'*Total: {len(files)} documents*')
    
    with open(moc_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    return moc_path

def export_to_obsidian(memory_dir: Path, output_dir: Path):
    """Export ทั้งหมดเป็น Obsidian Vault"""
    
    print('Exporting HAX-Mind Memory to Obsidian Vault...')
    print(f'   Source: {memory_dir}')
    print(f'   Output: {output_dir}')
    print()
    
    # สร้างโครงสร้างโฟลเดอร์
    folders = {
        'decisions': output_dir / '🎯 Decisions',
        'dreams': output_dir / '💭 Dreams',
        'notes': output_dir / '📝 Notes',
        'research': output_dir / '🔬 Research',
        'repo_knowledge': output_dir / '📚 Repo Knowledge',
        'tools': output_dir / 'Tools',
        'indexes': output_dir / '📊 Indexes',
        'summaries': output_dir / '📈 Summaries',
    }
    
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    
    stats = {key: 0 for key in folders.keys()}
    all_files = []
    
    # Export Decisions
    print('[Decisions] Processing...')
    for json_file in (memory_dir / 'canonical' / 'decisions').glob('*.json'):
        if json_to_markdown(json_file, folders['decisions']):
            stats['decisions'] += 1
    
    # Export Dreams
    print('[Dreams] Processing...')
    for json_file in (memory_dir / 'canonical' / 'dreams').glob('*.json'):
        if json_to_markdown(json_file, folders['dreams']):
            stats['dreams'] += 1
    
    # Export Notes
    print('[Notes] Processing...')
    for json_file in (memory_dir / 'canonical' / 'notes').glob('*.json'):
        if json_to_markdown(json_file, folders['notes']):
            stats['notes'] += 1
    
    # Export Research
    print('[Research] Processing...')
    for json_file in (memory_dir / 'canonical' / 'research').glob('*.json'):
        if json_to_markdown(json_file, folders['research']):
            stats['research'] += 1
    
    # Export Repo Knowledge
    print('[Repo Knowledge] Processing...')
    for json_file in (memory_dir / 'canonical' / 'repo_knowledge').glob('*.json'):
        if json_to_markdown(json_file, folders['repo_knowledge']):
            stats['repo_knowledge'] += 1
    
    # Export Tools
    print('[Tools] Processing...')
    for json_file in (memory_dir / 'canonical' / 'tools').glob('*.json'):
        if json_to_markdown(json_file, folders['tools']):
            stats['tools'] += 1
    
    # Export Indexes
    print('[Indexes] Processing...')
    for json_file in (memory_dir / 'indexes').glob('*.json'):
        if json_to_markdown(json_file, folders['indexes']):
            stats['indexes'] += 1
    
    # Copy existing markdown files
    print('[Summaries] Copying existing Markdown files...')
    for md_file in memory_dir.rglob('*.md'):
        if 'obsidian' not in str(md_file).lower():
            target = folders['summaries'] / sanitize_filename(md_file.name)
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                with open(target, 'w', encoding='utf-8') as f:
                    f.write(content)
                stats['summaries'] += 1
            except:
                pass
    
    # Create MOCs
    print('[MOC] Creating Maps of Content...')
    for key, folder in folders.items():
        if folder.exists():
            md_files = list(folder.glob('*.md'))
            if md_files:
                create_moc(
                    folder, 
                    f'{key.replace("_", " ").title()} Index',
                    md_files,
                    f'Map of Content for {key.replace("_", " ")}'
                )
    
    # Create Main Index
    print('[Index] Creating Main Index...')
    create_main_index(output_dir, stats)
    
    print()
    print('[DONE] Export Complete!')
    print()
    print('Statistics:')
    for key, count in stats.items():
        print(f'  {key}: {count} documents')
    print(f'  Total: {sum(stats.values())} documents')
    print()
    print('Next steps:')
    print(f'  1. Open folder: {output_dir}')
    print(f'  2. In Obsidian: Open folder as vault')
    print(f'  3. View Graph (Ctrl/Cmd+G) to see connections')

def create_main_index(vault_dir: Path, stats: dict):
    """สร้างหน้าแรกของ Vault"""
    index_path = vault_dir / '🏠 HAX-Mind Knowledge Base.md'
    
    lines = [
        '# 🏠 HAX-Mind Knowledge Base',
        '',
        f'*Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}*',
        '',
        '## 📊 Overview',
        '',
        '| Category | Count |',
        '|----------|-------|',
    ]
    
    emoji_map = {
        'decisions': '🎯',
        'dreams': '💭',
        'notes': '📝',
        'research': '🔬',
        'repo_knowledge': '📚',
        'tools': '🛠️',
        'indexes': '📊',
        'summaries': '📈',
    }
    
    for key, count in stats.items():
        if count > 0:
            folder_name = key.replace('_', ' ').title()
            lines.append(f'| {emoji_map.get(key, "📄")} [[📋 {folder_name} Index|{folder_name}]] | {count} |')
    
    lines.extend([
        '',
        f'| **Total** | **{sum(stats.values())}** |',
        '',
        '## 🔍 Quick Navigation',
        '',
        '### 🎯 Key Decisions',
        '- Review [[📋 Decisions Index|all decisions]]',
        '',
        '### 💭 Recent Dreams',
        '- View [[📋 Dreams Index|dream logs]]',
        '',
        '### 🔬 Research Topics',
        '- Browse [[📋 Research Index|research findings]]',
        '',
        '### 🛠️ Tools Knowledge',
        '- Explore [[📋 Tools Index|tools]]',
        '',
        '## 🕸️ Knowledge Graph',
        '',
        'Press `Ctrl/Cmd + G` to view the interactive knowledge graph showing connections between concepts.',
        '',
        '## 🔄 Auto-Learning',
        '',
        'This knowledge base is continuously updated by HAX-Mind auto-learning system.',
        '',
        '---',
        '',
        '*Powered by [Obsidian](https://obsidian.md) + HAX-Mind*',
    ])
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

if __name__ == '__main__':
    import sys
    
    # Paths
    root = Path(__file__).resolve().parent.parent
    memory_dir = root / 'memory'
    obsidian_dir = root / 'memory' / 'obsidian_vault'
    
    # Clean old export (skip if permission denied)
    if obsidian_dir.exists():
        import shutil
        try:
            shutil.rmtree(obsidian_dir)
        except PermissionError:
            print('Warning: Could not clean old export, continuing...')
    
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    
    # Export
    export_to_obsidian(memory_dir, obsidian_dir)
    
    print(f'\nVault location: {obsidian_dir}')
