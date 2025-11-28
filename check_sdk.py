from twelvelabs import TwelveLabs
import os
from dotenv import load_dotenv

load_dotenv()

client = TwelveLabs(api_key=os.environ.get('TWELVELABS_API_KEY'))

print("Client methods:", [m for m in dir(client) if not m.startswith('_')])
print("\nGenerate attribute:", hasattr(client, 'generate'))

if hasattr(client, 'generate'):
    print("Generate methods:", [m for m in dir(client.generate) if not m.startswith('_')])
    
    if hasattr(client.generate, 'text'):
        print("\nGenerate.text methods:", [m for m in dir(client.generate.text) if not m.startswith('_')])

