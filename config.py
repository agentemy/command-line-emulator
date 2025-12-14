import re
import sys
import yaml
import argparse
from pathlib import Path

class SimpleConfigParser:
    def __init__(self):
        self.constants = {}

    def _normalize_arrays(self, text):
        import re
        
        def replace_array(match):
            content = match.group(1).strip()
            if content and not '=' in content and not 'table(' in content:
                return f"'({content})"
            else:
                return match.group(0)
        
        pattern = r'\(\s*((?:(?:"[^"]*"|\'[^\']*\'|[^)])+?)\s*)\)'
        text = re.sub(pattern, replace_array, text)
        return text

    def _replace_constants_in_structure(self, data):
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                result[key] = self._replace_constants_in_structure(value)
            return result
        elif isinstance(data, list):
            return [self._replace_constants_in_structure(item) for item in data]
        elif isinstance(data, str):
            match = re.match(r'^\{([a-zA-Z][_a-zA-Z0-9]*)\}$', data.strip())
            if match:
                const_name = match.group(1)
                if const_name in self.constants:
                    return self.constants[const_name]
            
            for const_name, const_value in self.constants.items():
                placeholder = f'{{{const_name}}}'
                if placeholder in data:
                    if data == placeholder:
                        return const_value
                    else:
                        return data.replace(placeholder, str(const_value))
            
            return data
        else:
            return data    
    
    def parse(self, text):
        text = re.sub(r'<#.*?#>', '', text, flags=re.DOTALL)

        text = self._normalize_arrays(text)
        
        lines = text.strip().split('\n')
        
        non_const_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('var '):
                line = line[3:].strip().rstrip(';')
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    name, value = parts
                    
                    if not self._is_valid_name(name):
                        raise ValueError(f"Некорректное имя константы: {name}")
                    
                    parsed_value = self._parse_value_without_constants(value.strip())
                    self.constants[name] = parsed_value
            else:
                non_const_lines.append(line)
        
        combined_text = '\n'.join(non_const_lines)
        
        for const_name, const_value in self.constants.items():
            placeholder = f'{{{const_name}}}'
            if isinstance(const_value, str):
                replacement = f'"{const_value}"'
            else:
                replacement = str(const_value)
            
            pattern = r'\{\s*' + re.escape(const_name) + r'\s*\}'
            combined_text = re.sub(pattern, replacement, combined_text)
        
        result = {}
        i = 0
        while i < len(non_const_lines):
            line = non_const_lines[i].strip()
            if not line:
                i += 1
                continue
                
            if line.replace(',', '').strip() == '':
                i += 1
                continue
                
            if '=' in line:
                line = line.rstrip(';')
                
                equals_pos = line.find('=')
                key_part = line[:equals_pos].strip()
                value_part = line[equals_pos + 1:].strip()
                
                if self._is_valid_name(key_part):
                    full_value_parts = [value_part]
                    current_depth = 0
                    
                    current_depth += value_part.count('[') - value_part.count(']')
                    current_depth += value_part.count('(') - value_part.count(')')
                    
                    while i + 1 < len(non_const_lines) and current_depth > 0:
                        next_line = non_const_lines[i + 1].strip()
                        full_value_parts.append(next_line)
                        current_depth += next_line.count('[') - next_line.count(']')
                        current_depth += next_line.count('(') - next_line.count(')')
                        i += 1
                    
                    full_value = ' '.join(full_value_parts)
                    
                    full_value = full_value.rstrip(';').strip()
                    
                    parsed_value = self._parse_single_value(full_value)
                    result[key_part] = parsed_value
            
            i += 1
        
        result = self._replace_constants_in_structure(result)
        return result
    
    def _parse_value_without_constants(self, value_str):
        value_str = value_str.strip()
        
        if not value_str:
            return ""
        
        if re.match(r'^-?\d+$', value_str):
            return int(value_str)
        
        if value_str.lower() in ['true', 'false']:
            return value_str.lower() == 'true'
        
        if (len(value_str) >= 2 and 
            ((value_str.startswith('"') and value_str.endswith('"')) or 
             (value_str.startswith("'") and value_str.endswith("'")))):
            return value_str[1:-1]
        
        if value_str.startswith("'("):
            return self._parse_array(value_str, parse_constants=False)
        
        if value_str.startswith('table('):
            return self._parse_table(value_str, parse_constants=False)
        
        return value_str
    
    def _parse_single_value(self, value_str, parse_constants=True):
        value_str = value_str.strip()
        
        if not value_str:
            return ""
        
        if re.match(r'^-?\d+$', value_str):
            return int(value_str)
        
        if value_str.lower() in ['true', 'false']:
            return value_str.lower() == 'true'
        
        if (len(value_str) >= 2 and 
            ((value_str.startswith('"') and value_str.endswith('"')) or 
             (value_str.startswith("'") and value_str.endswith("'")))):
            return value_str[1:-1]
        
        if value_str.startswith("'("):
            return self._parse_array(value_str, parse_constants)
        
        if value_str.startswith('table('):
            return self._parse_table(value_str, parse_constants)
        
        return value_str
    
    def _parse_array(self, array_str, parse_constants=True):
        content = array_str[2:].rstrip(')').strip()
        if not content:
            return []
        
        items = []
        current = ""
        depth = 0
        in_quotes = False
        quote_char = None
        
        for char in content:
            if char in ['"', "'"]:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif quote_char == char:
                    in_quotes = False
                    quote_char = None
                current += char
            elif not in_quotes:
                if char == '(' or char == '[':
                    depth += 1
                elif char == ')' or char == ']':
                    depth -= 1
                elif char == ' ' and depth == 0:
                    if current:
                        if parse_constants:
                            items.append(self._parse_single_value(current))
                        else:
                            items.append(self._parse_value_without_constants(current))
                        current = ""
                    continue
                current += char
            else:
                current += char
        
        if current:
            if parse_constants:
                items.append(self._parse_single_value(current))
            else:
                items.append(self._parse_value_without_constants(current))
        
        return items
    
    def _parse_table(self, table_str, parse_constants=True):
        match = re.search(r'table\(\s*\[\s*(.*?)\s*\]\s*\)', table_str, re.DOTALL)
        if not match:
            return {}
        
        content = match.group(1).strip()
        if not content:
            return {}
        
        result = {}
        
        lines = []
        current = ''
        depth = 0
        in_quotes = False
        quote_char = None
        
        for char in content:
            if char in ['"', "'"]:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif quote_char == char:
                    in_quotes = False
                    quote_char = None
                current += char
            elif not in_quotes:
                if char == '[':
                    depth += 1
                elif char == ']':
                    depth -= 1
                elif char == ',' and depth == 0:
                    lines.append(current.strip())
                    current = ''
                    continue
                current += char
            else:
                current += char
        
        if current.strip():
            lines.append(current.strip())
        
        for line in lines:
            line = line.strip()
            if not line or line == ',':
                continue
            
            if line.endswith(','):
                line = line[:-1].strip()
            
            if '=' in line:
                key = ''
                value = ''
                in_quotes_local = False
                quote_char_local = None
                equals_found = False
                
                for char in line:
                    if char in ['"', "'"]:
                        if not in_quotes_local:
                            in_quotes_local = True
                            quote_char_local = char
                        elif quote_char_local == char:
                            in_quotes_local = False
                            quote_char_local = None
                        
                        if not equals_found:
                            key += char
                        else:
                            value += char
                    elif char == '=' and not in_quotes_local:
                        equals_found = True
                    else:
                        if not equals_found:
                            key += char
                        else:
                            value += char
                
                key = key.strip()
                value = value.strip()
                if not self._is_valid_name(key):
                    raise ValueError(f"Некорректное имя ключа в словаре: {key}")
                if parse_constants:
                    parsed_value = self._parse_single_value(value)
                else:
                    parsed_value = self._parse_value_without_constants(value)
                result[key] = parsed_value   
        return result
    
    def _is_valid_name(self, name):
        return bool(re.match(r'^[a-zA-Z][_a-zA-Z0-9]*$', name))
    
    def parse_file(self, filename):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse(content)


def main():
    parser = argparse.ArgumentParser(description='Преобразование конфигурации в YAML')
    parser.add_argument('-i', '--input', required=True, help='Входной файл')
    parser.add_argument('-o', '--output', required=True, help='Выходной файл YAML')
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"Ошибка: файл {input_path} не найден", file=sys.stderr)
        sys.exit(1)
    
    try:
        config_parser = SimpleConfigParser()
        config = config_parser.parse_file(str(input_path))
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"Конфигурация успешно преобразована и сохранена в {output_path}")
        
        print("\nСодержимое YAML файла:")
        print("=" * 50)
        print(yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False))
        
    except Exception as e:
        print(f"Ошибка при обработке файла: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()