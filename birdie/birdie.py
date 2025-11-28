import pygame
import numpy as np
import random
import math
import os

# Инициализация Pygame
pygame.init()

# Константы экрана
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60

# Цвета
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
BLUE = (135, 206, 235)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
PIPE_GREEN = (0, 128, 0)
GROUND_BROWN = (139, 69, 19)

# Константы игры
GRAVITY = 0.5
FLAP_STRENGTH = -8
PIPE_WIDTH = 80
PIPE_GAP = 150
PIPE_SPEED = 3

# Настройки ГА
POPULATION_SIZE = 50
MUTATION_RATE = 0.1
ELITE_SIZE = 10  # Топ птицы, которые проходят в следующее поколение

class NeuralNetwork:
    """Простая нейронная сеть для принятия решений твоих птиц"""
    
    def _init_(self, input_size=4, hidden_size=8, output_size=1):
        # Инициализация весов случайными значениями
        self.weights_input_hidden = np.random.uniform(-1, 1, (input_size, hidden_size))
        self.weights_hidden_output = np.random.uniform(-1, 1, (hidden_size, output_size))
        self.bias_hidden = np.random.uniform(-1, 1, (1, hidden_size))
        self.bias_output = np.random.uniform(-1, 1, (1, output_size))
        
    def sigmoid(self, x):
        # Избегаем переполнения
        x = np.clip(x, -500, 500)
        return 1 / (1 + np.exp(-x))
    
    def predict(self, inputs):
        # Прямое распространение
        inputs = np.array(inputs).reshape(1, -1)
        
        # Скрытый слой
        hidden = np.dot(inputs, self.weights_input_hidden) + self.bias_hidden
        hidden = self.sigmoid(hidden)
        
        # Выходной слой
        output = np.dot(hidden, self.weights_hidden_output) + self.bias_output
        output = self.sigmoid(output)
        
        return output[0][0] > 0.5  # True если птица должна прыгнуть
    
    def copy(self):
        """Создает копию нейросети"""
        new_net = NeuralNetwork()
        new_net.weights_input_hidden = self.weights_input_hidden.copy()
        new_net.weights_hidden_output = self.weights_hidden_output.copy()
        new_net.bias_hidden = self.bias_hidden.copy()
        new_net.bias_output = self.bias_output.copy()
        return new_net

class Bird:
    """Класс всех"""
    
    def _init_(self, x, y, brain=None):
        self.x = x
        self.y = y
        self.velocity_y = 0
        self.alive = True
        self.fitness = 0
        self.brain = brain if brain else NeuralNetwork()
        self.color = (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
        
    def flap(self):
        self.velocity_y = FLAP_STRENGTH
        
    def update(self):
        if not self.alive:
            return
            
        # Применяем гравитацию
        self.velocity_y += GRAVITY
        self.y += self.velocity_y
        
        # Проверяем границы экрана
        if self.y > SCREEN_HEIGHT - 50 or self.y < 0:
            self.alive = False
            
    def get_inputs(self, pipes):
        """Получает входные данные для нейросети"""
        if not pipes:
            return [0, 0, 0, self.velocity_y / 10]
            
        # Находим ближайшую трубу
        next_pipe = None
        for pipe in pipes:
            if pipe.x + PIPE_WIDTH > self.x:
                next_pipe = pipe
                break
                
        if not next_pipe:
            return [0, 0, 0, self.velocity_y / 10]
            
        # Входные данные для ИИ:
        # 1. Горизонтальное расстояние до трубы
        # 2. Вертикальное расстояние до верхней части просвета
        # 3. Вертикальное расстояние до нижней части просвета  
        # 4. Вертикальная скорость птицы
        
        horizontal_distance = (next_pipe.x - self.x) / SCREEN_WIDTH
        gap_center = next_pipe.y + PIPE_GAP / 2
        distance_to_gap_top = (self.y - next_pipe.y) / SCREEN_HEIGHT
        distance_to_gap_bottom = (gap_center - self.y) / SCREEN_HEIGHT
        velocity_normalized = self.velocity_y / 10
        
        return [horizontal_distance, distance_to_gap_top, distance_to_gap_bottom, velocity_normalized]
    
    def think(self, pipes):
        """Принимаю решение"""
        if not self.alive:
            return
            
        inputs = self.get_inputs(pipes)
        if self.brain.predict(inputs):
            self.flap()
            
    def draw(self, screen):
        if self.alive:
            pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), 15)
            # Глаз
            pygame.draw.circle(screen, WHITE, (int(self.x + 5), int(self.y - 3)), 4)
            pygame.draw.circle(screen, BLACK, (int(self.x + 7), int(self.y - 3)), 2)

class Pipe:
    """Класс трубы"""
    
    def _init_(self, x, y):
        self.x = x
        self.y = y  # y координата верхней части просвета
        
    def update(self):
        self.x -= PIPE_SPEED
        
    def draw(self, screen):
        # Верхняя труба
        pygame.draw.rect(screen, PIPE_GREEN, (self.x, 0, PIPE_WIDTH, self.y))
        pygame.draw.rect(screen, BLACK, (self.x, 0, PIPE_WIDTH, self.y), 2)
        
        # Нижняя труба
        pygame.draw.rect(screen, PIPE_GREEN, (self.x, self.y + PIPE_GAP, PIPE_WIDTH, SCREEN_HEIGHT - self.y - PIPE_GAP))
        pygame.draw.rect(screen, BLACK, (self.x, self.y + PIPE_GAP, PIPE_WIDTH, SCREEN_HEIGHT - self.y - PIPE_GAP), 2)
        
    def collides_with(self, bird):
        if not bird.alive:
            return False
            
        bird_rect = pygame.Rect(bird.x - 15, bird.y - 15, 30, 30)
        top_pipe = pygame.Rect(self.x, 0, PIPE_WIDTH, self.y)
        bottom_pipe = pygame.Rect(self.x, self.y + PIPE_GAP, PIPE_WIDTH, SCREEN_HEIGHT - self.y - PIPE_GAP)
        
        return bird_rect.colliderect(top_pipe) or bird_rect.colliderect(bottom_pipe)

class Population:
    """Класс популяции птиц для генетического алгоритма"""
    
    def _init_(self, size):
        self.size = size
        self.birds = [Bird(100, SCREEN_HEIGHT // 2) for _ in range(size)]
        self.generation = 1
        self.alive_count = size
        self.best_fitness = 0
        self.average_fitness = 0
        
    def update(self, pipes):
        self.alive_count = 0
        for bird in self.birds:
            if bird.alive:
                bird.think(pipes)
                bird.update()
                bird.fitness += 0.1  # Награда за выживание
                
                # Проверка столкновений
                for pipe in pipes:
                    if pipe.collides_with(bird):
                        bird.alive = False
                        
                if bird.alive:
                    self.alive_count += 1
                    
    def all_dead(self):
        return self.alive_count == 0
    
    def calculate_fitness(self):
        """Подсчет приспособленности"""
        total_fitness = 0
        max_fitness = 0
        
        for bird in self.birds:
            total_fitness += bird.fitness
            if bird.fitness > max_fitness:
                max_fitness = bird.fitness
                
        self.best_fitness = max_fitness
        self.average_fitness = total_fitness / len(self.birds)
    
    def selection(self):
        """Отбор лучших"""
        # Сортируем по приспособленности
        self.birds.sort(key=lambda x: x.fitness, reverse=True)
        return self.birds[:ELITE_SIZE]
    
    def crossover(self, parent1, parent2):
        """Скрещивание двух родителей"""
        child_brain = NeuralNetwork()
        
        # Смешиваем веса родителей
        mask1 = np.random.rand(*parent1.brain.weights_input_hidden.shape) < 0.5
        mask2 = np.random.rand(*parent1.brain.weights_hidden_output.shape) < 0.5
        mask3 = np.random.rand(*parent1.brain.bias_hidden.shape) < 0.5
        mask4 = np.random.rand(*parent1.brain.bias_output.shape) < 0.5
        
        child_brain.weights_input_hidden = np.where(mask1, parent1.brain.weights_input_hidden, parent2.brain.weights_input_hidden)
        child_brain.weights_hidden_output = np.where(mask2, parent1.brain.weights_hidden_output, parent2.brain.weights_hidden_output)
        child_brain.bias_hidden = np.where(mask3, parent1.brain.bias_hidden, parent2.brain.bias_hidden)
        child_brain.bias_output = np.where(mask4, parent1.brain.bias_output, parent2.brain.bias_output)
        
        return Bird(100, SCREEN_HEIGHT // 2, child_brain)
    
    def mutate(self, bird):
        """Мутация птиц"""
        if random.random() < MUTATION_RATE:
            # Мутируем веса с небольшой вероятностью
            mutation_strength = 0.2
            
            bird.brain.weights_input_hidden += np.random.normal(0, mutation_strength, bird.brain.weights_input_hidden.shape)
            bird.brain.weights_hidden_output += np.random.normal(0, mutation_strength, bird.brain.weights_hidden_output.shape)
            bird.brain.bias_hidden += np.random.normal(0, mutation_strength, bird.brain.bias_hidden.shape)
            bird.brain.bias_output += np.random.normal(0, mutation_strength, bird.brain.bias_output.shape)
    
    def next_generation(self):
        """Создание нового поклтения"""
        self.calculate_fitness()
        elite = self.selection()
        
        new_birds = []
        
        # Элитные птицы проходят без изменений
        for bird in elite:
            new_bird = Bird(100, SCREEN_HEIGHT // 2, bird.brain.copy())
            new_birds.append(new_bird)
        
        # Заполняем остальную популяцию потомками элиты
        while len(new_birds) < self.size:
            parent1 = random.choice(elite)
            parent2 = random.choice(elite)
            child = self.crossover(parent1, parent2)
            self.mutate(child)
            new_birds.append(child)
        
        self.birds = new_birds
        self.generation += 1
        self.alive_count = self.size
    
    def get_best_bird(self):
        """Возвращает лучшую живую птицу"""
        best_bird = None
        best_fitness = -1
        
        for bird in self.birds:
            if bird.alive and bird.fitness > best_fitness:
                best_fitness = bird.fitness
                best_bird = bird
                
        return best_bird

class FlappyBirdAI:
    """Главный класс игры"""
    
    def _init_(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Попрыгаем")
        self.clock = pygame.time.Clock()
        
        # Игровые объекты
        self.population = Population(POPULATION_SIZE)
        self.pipes = []
        self.pipe_timer = 0
        self.score = 0
        
        # Шрифты
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        
    def add_pipe(self):
        """Добавляет новую трубу"""
        gap_y = random.randint(100, SCREEN_HEIGHT - PIPE_GAP - 100)
        self.pipes.append(Pipe(SCREEN_WIDTH, gap_y))
        
    def draw_background(self):
        """Отрисовка фона"""
        # Небо
        self.screen.fill(BLUE)
        
        # Облака (простые)
        for i in range(5):
            x = (i * 200 + (pygame.time.get_ticks() // 50) % 200) % SCREEN_WIDTH
            y = 50 + i * 30
            pygame.draw.ellipse(self.screen, WHITE, (x, y, 80, 40))
            pygame.draw.ellipse(self.screen, WHITE, (x + 20, y - 10, 60, 30))
            pygame.draw.ellipse(self.screen, WHITE, (x + 40, y, 80, 40))
        
        # Земля
        pygame.draw.rect(self.screen, GROUND_BROWN, (0, SCREEN_HEIGHT - 50, SCREEN_WIDTH, 50))
        pygame.draw.rect(self.screen, (101, 67, 33), (0, SCREEN_HEIGHT - 50, SCREEN_WIDTH, 10))
        
    def draw_ui(self):
        """Отрисовка интерфейса"""
        # Информация о поколении
        gen_text = self.font.render(f"Поколение: {self.population.generation}", True, WHITE)
        self.screen.blit(gen_text, (10, 10))
        
        # Живые птицы
        alive_text = self.font.render(f"Живые: {self.population.alive_count}/{POPULATION_SIZE}", True, WHITE)
        self.screen.blit(alive_text, (10, 50))
        
        # Лучший результат
        best_text = self.font.render(f"Лучший результат: {self.population.best_fitness:.1f}", True, WHITE)
        self.screen.blit(best_text, (10, 90))
        
        # Средний результат
        avg_text = self.font.render(f"Средний результат: {self.population.average_fitness:.1f}", True, WHITE)
        self.screen.blit(avg_text, (10, 130))
        
        # Инструкции
        instruction1 = self.small_font.render("SPACE - Пауза/Продолжить", True, WHITE)
        instruction2 = self.small_font.render("R - Обучение", True, WHITE)
        instruction3 = self.small_font.render("ESC - Выход", True, WHITE)
        
        self.screen.blit(instruction1, (SCREEN_WIDTH - 250, 10))
        self.screen.blit(instruction2, (SCREEN_WIDTH - 250, 35))
        self.screen.blit(instruction3, (SCREEN_WIDTH - 250, 60))
        
        # Показываем лучшую птицу
        best_bird = self.population.get_best_bird()
        if best_bird:
            outline_color = tuple(min(255, int(c * 1.5)) for c in best_bird.color)
            pygame.draw.circle(self.screen, outline_color, (int(best_bird.x), int(best_bird.y)), 18, 3)
    
    def run(self):
        running = True
        paused = False
        fast_mode = False
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        paused = not paused
                    elif event.key == pygame.K_r:
                        fast_mode = not fast_mode
                    elif event.key == pygame.K_ESCAPE:
                        running = False
            
            if not paused:
                # Добавляем трубы
                self.pipe_timer += 1
                if self.pipe_timer >= 90:  # Новая труба каждые 1.5 секунды
                    self.add_pipe()
                    self.pipe_timer = 0
                
                # Обновляем трубы
                for pipe in self.pipes[:]:
                    pipe.update()
                    if pipe.x + PIPE_WIDTH < 0:
                        self.pipes.remove(pipe)
                        self.score += 1
                
                # Обновляем популяцию
                self.population.update(self.pipes)
                
                # Если все птицы мертвы, создаем новое поколение
                if self.population.all_dead():
                    self.population.next_generation()
                    self.pipes.clear()
                    self.pipe_timer = 0
                    self.score = 0
            
            # Отрисовка (пропускаем в быстром режиме для ускорения обучения)
            if not fast_mode or self.population.generation % 10 == 0:
                self.draw_background()
                
                # Рисуем трубы
                for pipe in self.pipes:
                    pipe.draw(self.screen)
                
                # Рисуем птиц
                for bird in self.population.birds:
                    bird.draw(self.screen)
                
                self.draw_ui()
                
                if paused:
                    pause_text = self.font.render("ПАУЗА", True, WHITE)
                    text_rect = pause_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
                    pygame.draw.rect(self.screen, BLACK, text_rect.inflate(20, 10))
                    self.screen.blit(pause_text, text_rect)
                
                if fast_mode:
                    fast_text = self.small_font.render("ОБУЧЕНИЕ", True, YELLOW)
                    self.screen.blit(fast_text, (SCREEN_WIDTH//2 - 80, SCREEN_HEIGHT - 30))
                
                pygame.display.flip()
            if not fast_mode:
                self.clock.tick(FPS)
        
        pygame.quit()

if _name_ == "_main_":
    print("Добро пожаловать")
    print("вот и наблюдайте, как он учатся играть")
    print("\nУправление:")
    print("SPACE - Пауза/Продолжить")
    print("R - Обучение")
    print("ESC - Выход")
    print("\nНачинает обучение...")
    
    game = FlappyBirdAI()
    game.run()