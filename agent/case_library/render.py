from jinja2 import Template


def render_embedding_input_template(
    template,
    description,
):
    """
    渲染 j2 模板 根据 template 分为 case 和 query
    """
    template_str = open(template).read()
    template = Template(template_str)

    return template.render(
        description=description,
    )
