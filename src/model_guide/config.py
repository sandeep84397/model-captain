from .evaluation import validate_config

STARTER_CONFIG={"version":1,"candidates":[{"id":"demo","provider":"demo","model":"synthetic-v1","max_output_tokens":256},{"id":"openai-example","provider":"openai","model":"replace-me","max_output_tokens":512},{"id":"anthropic-example","provider":"anthropic","model":"replace-me","max_output_tokens":512}]}

def load_config(value): return validate_config(value)
