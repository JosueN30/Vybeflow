
# VybeFlow Messaging App

Welcome to the VybeFlow Messaging App! This application allows users to send messages, share posts, and customize emojis for a personalized social experience.

## Features

- User registration and authentication
- Upload images with captions
- View a feed of posts from all users
- Send and receive messages in real-time
- Customize emojis by adding, editing, and deleting them
- User-friendly chat interface
- Secure session management
- Responsive design with HTML templates

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
   flask db upgrade
   ```

4. Run the application:
   ```
   flask run
   ```

## Usage

- Navigate to `http://localhost:5000` in your web browser to access the application.
- Register a new account or log in with an existing account.
- Start chatting, sharing posts, and customizing your emojis!

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any suggestions or improvements.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

- **Registration:** Navigate to the registration page to create a new account.
- **Login:** Use your credentials to log in to your account.
- **Upload Posts:** After logging in, you can upload images with captions to share with other users.
- **View Feed:** The feed displays all posts from users, allowing you to see what others are sharing.

## Database

The application uses SQLite for data storage. The database file `vybeflow.db` will be created automatically upon running the application for the first time. 

## Directory Structure

```
vybe-flow
├── app.py                # Main application file
├── requirements.txt      # Project dependencies
├── README.md             # Project documentation
├── vybeflow.db           # SQLite database file
├── static                # Directory for static files
│   └── uploads           # Directory for uploaded images
├── templates             # Directory for HTML templates
│   ├── base.html         # Base template
│   ├── feed.html         # Feed display template
│   ├── login.html        # Login form template
│   ├── register.html     # Registration form template
│   └── upload.html       # Upload post form template
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any suggestions or improvements.