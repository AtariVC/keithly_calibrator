


def widget_led_on() -> str:
    led_on = "QWidget{\n\
        background-color: #32CD32;\n\
       border-radius: 8px;\n\
        border: 1px solid #208420;\n\
    	max-width: 14px; \n\
    	max-height: 14px;\n\
    	min-width: 14px; \n\
    	min-height: 14px;\n\
    }"
    return led_on

def widget_led_off() -> str:
    led_off = "QWidget{\n\
        background-color: #8C8C8C;\n\
       border-radius: 8px;\n\
        border: 1px solid #6C6060;\n\
    	max-width: 14px; \n\
    	max-height: 14px;\n\
    	min-width: 14px; \n\
    	min-height: 14px;\n\
    }"
    return led_off