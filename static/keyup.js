function keyboard(event) {
    let keycode = event.keyCode;
    if (keycode == 37) {
        document.getElementById("previous").click();
    } else if (keycode == 39) {
        document.getElementById("next").click();
    } else if (keycode == 13) {
        document.getElementById("catalog").click();
    }
}
document.addEventListener("keyup", keyboard);
