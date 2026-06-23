from typing import Optional

class NameSuggestionEngine:
    def __init__(self, model_name: str = "google/mt5-small"):
        self.model_name = model_name
        self._generator = None

    def _load_generator(self):
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "transformers is required for name suggestion; install it only when needed."
            ) from exc

        self._generator = pipeline(
            "text2text-generation",
            model=self.model_name,
            tokenizer=self.model_name,
            device=-1
        )

    def suggest(self, name: str, locale: Optional[str] = None) -> Optional[str]:
        if not name:
            return None

        if self._generator is None:
            self._load_generator()

        prompt = (
            "Normalize this personal name for indexing. "
            "Return the inverted form if appropriate.\n\n"
            f"Name: {name}\n"
            "Indexed form:"
        )

        try:
            outputs = self._generator(prompt, max_length=64, num_return_sequences=1)
            if outputs and isinstance(outputs, list):
                return outputs[0].get("generated_text", "").strip()
        except Exception:
            pass

        return None