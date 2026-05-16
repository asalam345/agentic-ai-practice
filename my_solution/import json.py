import json
import hashlib

# Read the manifest
with open(r'C:\Users\abdus.salam\.ollama\models\manifests\registry.ollama.ai\library\qwen3\8b', 'r') as f:
    manifest = json.load(f)

print("🔍 QWEN3:8B MODEL BREAKDOWN")
print("="*50)
print(f"Schema Version: {manifest['schemaVersion']}")

# Analyze each layer
for i, layer in enumerate(manifest['layers'], 1):
    size_gb = layer['size'] / 1e9
    media_type = layer['mediaType'].split('.')[-1]
    
    print(f"\nLayer {i}: {media_type.upper()}")
    print(f"  Size: {size_gb:.2f} GB" if size_gb > 0.1 else f"  Size: {layer['size']} bytes")
    print(f"  Digest: {layer['digest'][:20]}...")
    
    if media_type == 'model':
        print(f"  ⭐ This is the MAIN model file!")
    elif media_type == 'template':
        print(f"  📝 Prompt template")
    elif media_type == 'params':
        print(f"  ⚙️  Model parameters")
    elif media_type == 'license':
        print(f"  📜 License information")

print("\n" + "="*50)
print(f"Total model size: {sum(l['size'] for l in manifest['layers']) / 1e9:.2f} GB")