import re
import sys
import yaml
import argparse
from typing import Dict, List, Any, Union, Optional
from pathlib import Path

class ConfigParser:
    def __init__(self):
        self.constants: Dict[str, Any] = {}
        
    def remove_comments(self, text: str) -> str:
        """Удаление многострочных комментариев"""
        # Удаляем многострочные комментарии <# ... #>
        pattern = r'<#.*?#>'
        return re.sub(pattern, '', text, flags=re.DOTALL)
    
    def parse_value(self, value_str: str) -> Any:
        """Парсинг значения (число, массив, словарь)"""
        value_str = value_str.strip()
        
        # Проверка на число
        if re.match(r'^-?\d+$', value_str):
            return int(value_str)
        
        # Проверка на массив
        if value_str.startswith("'("):
            return self.parse_array(value_str)
        
        # Проверка на словарь
        if value_str.startswith('table(['):
            return self.parse_dict(value_str)
        
        # Проверка на ссылку на константу
        if value_str.startswith('{') and value_str.endswith('}'):
            const_name = value_str[1:-1].strip()
            if const_name in self.constants:
                return self.constants[const_name]
            raise ValueError(f"Неизвестная константа: {const_name}")
        
        # Проверка на имя (для будущих расширений)
        if re.match(r'^[a-zA-Z][_a-zA-Z0-9]*$', value_str):
            return value_str
        
        raise ValueError(f"Некорректное значение: {value_str}")
    
    def parse_array(self, array_str: str) -> List[Any]:
        """Парсинг массива '(... )"""
        # Удаляем начальные и конечные символы
        content = array_str[2:-2].strip()  # Убираем "'( " и " )"
        if not content:
            return []
        
        # Разбиваем на значения
        values = []
        current = ""
        brace_count = 0
        bracket_count = 0
        in_quotes = False
        
        for char in content:
            if char == ',' and brace_count == 0 and bracket_count == 0 and not in_quotes:
                if current.strip():
                    values.append(self.parse_value(current.strip()))
                current = ""
            else:
                current += char
                if char == '(':
                    brace_count += 1
                elif char == ')':
                    brace_count -= 1
                elif char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                elif char == "'":
                    in_quotes = not in_quotes
        
        if current.strip():
            values.append(self.parse_value(current.strip()))
        
        return values
    
    def parse_dict(self, dict_str: str) -> Dict[str, Any]:
        """Парсинг словаря table([...])"""
        # Извлекаем содержимое внутри table([...])
        match = re.match(r'table\(\s*\[\s*(.*?)\s*\]\s*\)', dict_str, re.DOTALL)
        if not match:
            raise ValueError(f"Некорректный формат словаря: {dict_str}")
        
        content = match.group(1).strip()
        if not content:
            return {}
        
        result = {}
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        for line in lines:
            # Удаляем запятую в конце если есть
            if line.endswith(','):
                line = line[:-1].strip()
            
            # Разделяем имя и значение
            if '=' not in line:
                raise ValueError(f"Некорректная строка в словаре: {line}")
            
            name, value_str = line.split('=', 1)
            name = name.strip()
            value_str = value_str.strip()
            
            if not re.match(r'^[a-zA-Z][_a-zA-Z0-9]*$', name):
                raise ValueError(f"Некорректное имя: {name}")
            
            result[name] = self.parse_value(value_str)
        
        return result
    
    def process_constants(self, text: str) -> str:
        """Обработка объявлений констант var"""
        lines = text.split('\n')
        result_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Проверка на объявление константы
            if line.startswith('var '):
                # Объединение многострочных объявлений
                const_lines = [line]
                j = i + 1
                while j < len(lines) and not lines[j].strip().endswith(';'):
                    const_lines.append(lines[j].strip())
                    j += 1
                if j < len(lines):
                    const_lines.append(lines[j].strip())
                
                const_decl = ' '.join(const_lines)
                i = j
                
                # Парсинг объявления константы
                match = re.match(r'var\s+([a-zA-Z][_a-zA-Z0-9]*)\s+(.*?);', const_decl, re.DOTALL)
                if match:
                    const_name = match.group(1)
                    const_value_str = match.group(2).strip()
                    self.constants[const_name] = self.parse_value(const_value_str)
                else:
                    raise ValueError(f"Некорректное объявление константы: {const_decl}")
            else:
                result_lines.append(lines[i])
            
            i += 1
        
        return '\n'.join(result_lines)
    
    def replace_constants(self, text: str) -> str:
        """Замена ссылок на константы {имя} их значениями"""
        def replace_match(match):
            const_name = match.group(1).strip()
            if const_name in self.constants:
                value = self.constants[const_name]
                if isinstance(value, (int, list, dict)):
                    return str(value)
                return value
            raise ValueError(f"Неизвестная константа: {const_name}")
        
        return re.sub(r'\{([^}]+)\}', replace_match, text)
    
    def parse_config(self, text: str) -> Dict[str, Any]:
        """Основной парсинг конфигурации"""
        # Удаляем комментарии
        text = self.remove_comments(text)
        
        # Обрабатываем константы
        text = self.process_constants(text)
        
        # Заменяем ссылки на константы
        text = self.replace_constants(text)
        
        # Парсим оставшуюся конфигурацию
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        result = {}
        
        for line in lines:
            # Пропускаем пустые строки и обработанные константы
            if not line or line.startswith('var '):
                continue
            
            if '=' not in line:
                raise ValueError(f"Некорректная строка: {line}")
            
            name, value_str = line.split('=', 1)
            name = name.strip()
            value_str = value_str.strip()
            
            if not re.match(r'^[a-zA-Z][_a-zA-Z0-9]*$', name):
                raise ValueError(f"Некорректное имя: {name}")
            
            result[name] = self.parse_value(value_str)
        
        return result
    
    def parse_file(self, input_file: str) -> Dict[str, Any]:
        """Парсинг конфигурации из файла"""
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse_config(content)


def main():
    parser = argparse.ArgumentParser(
        description='Преобразование учебного конфигурационного языка в YAML'
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Путь к входному файлу конфигурации'
    )
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Путь к выходному YAML файлу'
    )
    
    args = parser.parse_args()
    
    # Проверяем существование входного файла
    if not Path(args.input).exists():
        print(f"Ошибка: входной файл '{args.input}' не найден", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Парсим конфигурацию
        config_parser = ConfigParser()
        config = config_parser.parse_file(args.input)
        
        # Сохраняем в YAML
        with open(args.output, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        print(f"Конфигурация успешно преобразована и сохранена в '{args.output}'")
        
    except Exception as e:
        print(f"Ошибка при обработке конфигурации: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()