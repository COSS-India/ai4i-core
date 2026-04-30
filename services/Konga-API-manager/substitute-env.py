#!/usr/bin/env python3
"""
Substitute environment variables in kong.yml
Replaces ${VAR_NAME} with actual environment variable values
"""
import os
import re
import sys

def substitute_env_vars(content):
    """Substitute ${VAR_NAME} with environment variable values"""
    def replace_var(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))  # Return original if not found
    
    # Pattern to match ${VAR_NAME}
    pattern = r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'
    return re.sub(pattern, replace_var, content)

def main():
    input_file = '/kong/kong.yml'
    output_file = '/kong/kong-substituted.yml'
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found", file=sys.stderr)
        sys.exit(1)
    
    # Read the original file
    with open(input_file, 'r') as f:
        content = f.read()
    
    # Substitute environment variables
    substituted = substitute_env_vars(content)
    
    # Write the substituted content
    with open(output_file, 'w') as f:
        f.write(substituted)
    
    print("Environment variables substituted successfully")
    print(f"Substituted config written to {output_file}")

if __name__ == '__main__':
    main()

