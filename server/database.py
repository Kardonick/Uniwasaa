import mysql.connector
from mysql.connector import pooling
import configparser
import bcrypt
import threading
import os

class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Database, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._connect()

    def _connect(self):
        config = configparser.ConfigParser()
        config.read(os.path.join(os.path.dirname(__file__), '../config.ini'))
        
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="mypool",
                pool_size=10,
                host=config['DATABASE']['host'],
                user=config['DATABASE']['user'],
                password=config['DATABASE']['password'],
                database=config['DATABASE']['database']
            )
            self._init_db()
            print("Database connected successfully (Pool initialized).")
        except mysql.connector.Error as err:
            print(f"Error connecting to database: {err}")
            raise

    def _get_connection(self):
        return self.pool.get_connection()

    def _init_db(self):
        """Creates necessary tables if they don't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `groups` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id INT,
                    user_id INT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (group_id, user_id),
                    FOREIGN KEY (group_id) REFERENCES `groups`(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            conn.commit()
            cursor.close()
        except mysql.connector.Error as err:
            print(f"Error creating tables: {err}")
        finally:
            conn.close()

    def register_user(self, username, password):
        """Registers a new user. Returns True if successful, False if username exists."""
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed))
            conn.commit()
            cursor.close()
            return True
        except mysql.connector.IntegrityError:
            return False
        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            return False
        finally:
            conn.close()

    def login_user(self, username, password):
        """Verifies user credentials. Returns User ID if successful, None otherwise."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                user_id, stored_hash = result
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')
                
                if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
                    return user_id
            return None
        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            return None
        finally:
            conn.close()

    def get_user_id(self, username):
        """Returns the user ID for a given username."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()
            cursor.close()
            if result:
                return result[0]
            return None
        except mysql.connector.Error as err:
            print(f"Database error getting user ID: {err}")
            return None
        finally:
            conn.close()

    def get_all_users(self):
        """Returns a list of all usernames."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users")
            users = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return users
        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            return []
        finally:
            conn.close()

    def create_group(self, name, creator_id):
        """Creates a new group and adds the creator as a member."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO `groups` (name) VALUES (%s)", (name,))
            group_id = cursor.lastrowid
            cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)", (group_id, creator_id))
            conn.commit()
            cursor.close()
            return group_id
        except mysql.connector.Error as err:
            print(f"Database error creating group: {err}")
            return None
        finally:
            conn.close()

    def add_group_member(self, group_id, user_id):
        """Adds a user to a group."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT IGNORE INTO group_members (group_id, user_id) VALUES (%s, %s)", (group_id, user_id))
            conn.commit()
            cursor.close()
            return True
        except mysql.connector.Error as err:
            print(f"Database error adding member: {err}")
            return False
        finally:
            conn.close()

    def get_user_groups(self, user_id):
        """Returns list of (group_id, group_name) for a user."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT g.id, g.name 
                FROM `groups` g 
                JOIN group_members gm ON g.id = gm.group_id 
                WHERE gm.user_id = %s
            """, (user_id,))
            groups = cursor.fetchall()
            cursor.close()
            return groups
        except mysql.connector.Error as err:
            print(f"Database error getting groups: {err}")
            return []
        finally:
            conn.close()

    def get_group_members(self, group_id):
        """Returns list of user_ids in a group."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM group_members WHERE group_id = %s", (group_id,))
            members = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return members
        except mysql.connector.Error as err:
            print(f"Database error getting members: {err}")
            return []
        finally:
            conn.close()

    def close(self):
        # Pool doesn't need explicit closing usually, but we can't close it easily.
        pass
