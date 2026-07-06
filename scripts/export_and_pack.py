import os
import sqlite3
import json
import shutil
import zipfile
import re

def clean_filename(name):
    # Keep only alphanumeric characters, spaces, dashes, and underscores
    name = re.sub(r'[^\w\s-]', '', name)
    # Replace spaces/whitespace with underscores and remove consecutive ones
    name = re.sub(r'[-\s]+', '_', name)
    return name.strip('_')

def export_workflows():
    db_path = os.path.expanduser('~/.n8n/database.sqlite')
    if not os.path.exists(db_path):
        print(f"Error: n8n database not found at {db_path}")
        return []

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query all workflows (including archived ones)
    cursor.execute("SELECT id, name, active, nodes, connections, settings, meta FROM workflow_entity")
    rows = cursor.fetchall()
    
    exported = []
    
    # Create output directory
    out_dir = "/Users/fly/Desktop/N8N-main/n8n_examples_package"
    os.makedirs(out_dir, exist_ok=True)
    
    for row in rows:
        wf_id, name, active, nodes_str, conn_str, settings_str, meta_str = row
        
        try:
            nodes = json.loads(nodes_str) if nodes_str else []
        except Exception as e:
            print(f"Warning: Failed to parse nodes for workflow {name}: {e}")
            nodes = []

        try:
            connections = json.loads(conn_str) if conn_str else {}
        except Exception as e:
            print(f"Warning: Failed to parse connections for workflow {name}: {e}")
            connections = {}

        try:
            settings = json.loads(settings_str) if settings_str else {}
        except Exception as e:
            print(f"Warning: Failed to parse settings for workflow {name}: {e}")
            settings = {}

        try:
            meta = json.loads(meta_str) if meta_str else {}
        except Exception as e:
            print(f"Warning: Failed to parse meta for workflow {name}: {e}")
            meta = {}
            
        wf_data = {
            "name": name,
            "active": bool(active),
            "nodes": nodes,
            "connections": connections,
            "settings": settings,
            "meta": meta
        }
        
        safe_name = clean_filename(name)
        file_name = f"{safe_name}_{wf_id}.json"
        file_path = os.path.join(out_dir, file_name)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(wf_data, f, ensure_ascii=False, indent=2)
            
        print(f"Exported: {name} -> {file_name}")
        exported.append(file_path)
        
    conn.close()
    return exported

def create_zip():
    pkg_dir = "/Users/fly/Desktop/N8N-main/n8n_examples_package"
    zip_path = "/Users/fly/Desktop/N8N-main/n8n_examples.zip"
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
        
    print(f"Creating zip archive at: {zip_path}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(pkg_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Compute relative path to keep folder structure in zip
                rel_path = os.path.relpath(file_path, pkg_dir)
                zipf.write(file_path, rel_path)
                print(f"Added to zip: {rel_path}")
                
    print(f"Zip created successfully at {zip_path}")
    
    # Cleanup package folder
    shutil.rmtree(pkg_dir)
    print("Cleaned up temporary package folder")

if __name__ == "__main__":
    print("--- Starting n8n Examples Packager ---")
    exported = export_workflows()
    if exported:
        create_zip()
        print("--- Packager finished successfully ---")
    else:
        print("Error: No workflows found to package")
