document.addEventListener("DOMContentLoaded", function() {
    const emojiInput = document.getElementById("emoji-input");
    const emojiList = document.getElementById("emoji-list");
    const customizeButton = document.getElementById("customize-button");

    // Function to add a new custom emoji
    function addCustomEmoji() {
        const emojiName = emojiInput.value.trim();
        if (emojiName) {
            const emojiItem = document.createElement("li");
            emojiItem.textContent = emojiName;
            emojiList.appendChild(emojiItem);
            emojiInput.value = ""; // Clear input field
        }
    }

    // Event listener for the customize button
    customizeButton.addEventListener("click", function() {
        addCustomEmoji();
    });

    // Allow pressing Enter to add emoji
    emojiInput.addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            addCustomEmoji();
        }
    });
});