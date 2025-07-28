# Vybeflow Messaging App

Welcome to the Vybeflow Messaging App! This application allows users to send messages and customize emojis for a personalized messaging experience.

## Features

- User authentication (login and registration)
- Send and receive messages in real-time
- Customize emojis by adding, editing, and deleting them
- User-friendly chat interface

## Project Structure

```
vybeflow-messaging-app
├── src
│   ├── app.py                # Entry point of the application
│   ├── models                # Contains database models
│   │   ├── __init__.py
│   │   ├── user.py           # User model
│   │   ├── message.py        # Message model
│   │   └── emoji.py          # Emoji model
│   ├── routes                # Contains route handlers
│   │   ├── __init__.py
│   │   ├── auth.py           # Authentication routes
│   │   ├── messaging.py      # Messaging routes
│   │   └── emoji.py          # Emoji customization routes
│   ├── templates             # HTML templates
│   │   ├── base.html         # Base template
│   │   ├── chat.html         # Chat interface template
│   │   ├── customize_emoji.html # Emoji customization template
│   │   └── login.html        # Login page template
│   ├── static                # Static files (CSS, JS)
│   │   ├── css
│   │   │   └── style.css     # CSS styles
│   │   └── js
│   │       └── main.js       # JavaScript functionality
│   └── config.py             # Configuration settings
├── requirements.txt           # Project dependencies
└── README.md                  # Project documentation
```

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/vybeflow-messaging-app.git
   cd vybeflow-messaging-app
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up the database:
   ```
   python src/app.py
   ```

4. Run the application:
   ```
   python src/app.py
   ```

## Usage

- Navigate to `http://localhost:5000` in your web browser to access the application.
- Register a new account or log in with an existing account.
- Start chatting with other users and customize your emojis!

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any suggestions or improvements.

## License

This project is licensed under the MIT License. See the LICENSE file for details.