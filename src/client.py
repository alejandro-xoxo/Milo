import sys
import httpx

def main():
    if len(sys.argv) < 2:
        print("Uso: python src/client.py \"<tu prompt aquí>\"")
        sys.exit(1)
        
    prompt = sys.argv[1]
    url = "http://localhost:8000/chat"
    
    print(f"🚀 Enviando prompt a MILO: '{prompt}'...")
    try:
        response = httpx.post(url, json={"prompt": prompt}, timeout=60.0)
        if response.status_code == 200:
            data = response.json()
            print("\n✨ === RESPUESTA DE MILO === ✨")
            print(data["response"])
            
            print("\n🔧 === HERRAMIENTAS EJECUTADAS === 🔧")
            if data["execution_log"]:
                for log in data["execution_log"]:
                    print(f"👉 Herramienta: {log['tool']} | Args: {log['args']}")
            else:
                print("Ninguna (Gemini respondió directamente sin usar herramientas)")
        else:
            print(f"\n❌ Error ({response.status_code}): {response.text}")
    except httpx.RequestError as exc:
        print(f"\n❌ Error de conexión al servidor: {exc}")
        print("💡 Consejo: Asegúrate de que el servidor FastAPI esté corriendo con: python -m src.main")

if __name__ == "__main__":
    main()
