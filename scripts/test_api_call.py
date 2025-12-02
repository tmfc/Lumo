
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import litellm

# Add project root to the Python path to allow importing from slackbot
sys.path.append(str(Path(__file__).parent.parent))

# By default, litellm can be very verbose. This is a way to silence some of the noise.
# You can comment this out if you need more detailed litellm logs.
litellm.set_verbose = False


def main():
    """
    A simple script to test if the LiteLLM API call to the configured model is successful.
    """
    print("--- LiteLLM API Call Test ---")
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get model from environment, default to gemini/gemini-2.5-flash
    model = os.getenv("LITELLM_MODEL", "gemini/gemini-2.5-flash")
    
    # Check for Gemini-specific API key if that's the model provider
    if "gemini" in model and not os.getenv("GEMINI_API_KEY"):
        # LiteLLM also supports GOOGLE_API_KEY
        if not os.getenv("GOOGLE_API_KEY"):
             print("\nWarning: Model is a Gemini model, but GEMINI_API_KEY or GOOGLE_API_KEY is not set in .env")
             # We still proceed, as litellm might be configured in other ways

    print(f"Attempting to call model: '{model}' via LiteLLM...")
    
    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "Hello, what is your name?"}],
            temperature=0.1,
            max_tokens=50,
            timeout=60  # Generous timeout for a simple call
        )
        
        print("\n✅ API Call Successful!")
        print("--------------------------")
        
        response_content = response.choices[0].message.content
        print(f"Model response: {response_content}")
        
        print("\n--- Token Usage ---")
        usage = response.usage
        print(f"Prompt tokens:      {usage.prompt_tokens}")
        print(f"Completion tokens:  {usage.completion_tokens}")
        print(f"Total tokens:       {usage.total_tokens}")
        print("-------------------")

    except Exception as e:
        import traceback
        print(f"\n❌ API Call Failed!")
        print("----------------------")
        print(f"An error occurred: {type(e).__name__}: {e}")
        print("\n--- Full Traceback ---")
        traceback.print_exc()
        print("------------------------")
        print("\nDebugging Tips:")
        print("1. Verify that your API key in the .env file is correct and has the right permissions.")
        print("2. For Gemini, ensure the key is stored under GEMINI_API_KEY or GOOGLE_API_KEY.")
        print("3. Check for any networking issues (proxies, firewalls) that might block the connection.")
        print("4. Ensure the model name you are using is correct and you have access to it.")

if __name__ == "__main__":
    main()
