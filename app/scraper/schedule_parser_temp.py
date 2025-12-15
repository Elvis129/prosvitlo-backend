# Тестова версія parse_queue_schedule з покращеним regex
import re

text = """
1 11. 6 27,5%
1.2. 6 23,3%
2 2.1 6 25,8 %
2.2. 7 29,2 %
3 3.1. 7 30,8 %
3.2. 7 28,3 56
4 4.1. 6 27,5 %
4.2, 6 26,7 %
5 5.1. 6 20,8 %
5.2. 6 25,8 96
6 6.1. 5 25,0%
6.2. 6 23,3 %
"""

# Покращений патерн
# Шукаємо: "6 6.2. 6 23,3 %" або "1 11. 6 27,5%" або "1.2. 6 23,3%"
queue_pattern = r'(?:^\d+\s+)?(\d+\.\d+\.?)\s+(\d+)\s+[\d,]+\s*%'

for line in text.split('\n'):
    matches = re.findall(queue_pattern, line)
    if matches:
        for match in matches:
            queue_num = match[0].rstrip('.')
            hours = int(match[1])
            print(f"Черга: {queue_num}, Години: {hours}")
