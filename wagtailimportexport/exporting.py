import json, re

from django.db.models.fields.related import ForeignKey
from wagtail.core.blocks.stream_block import StreamValue
from wagtail.core.blocks import PageChooserBlock, StreamBlock, StructBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.snippets.blocks import SnippetChooserBlock
from wagtail.images import get_image_model
from wagtail.documents.models import get_document_model
from wagtail.snippets.models import get_snippet_models
from wagtailimportexport.compat import Page

Image = get_image_model()
Document = get_document_model()
SNIPPET_MODELS = get_snippet_models()
CHOOSER_BLOCKS = [PageChooserBlock, ImageChooserBlock, DocumentChooserBlock, SnippetChooserBlock]


def export_pages(root_page, export_unpublished=False, include_linked_assets=False):
    """
    Create a JSON defintion of part of a site's page tree starting
    from root_page and descending into its descendants

    By default only published pages are exported.

    If a page is unpublished it and all its descendants are pruned even
    if some of those descendants are themselves published. This ensures
    that there are no orphan pages when the subtree is created in the
    destination site.

    If export_unpublished=True the root_page and all its descendants
    are included.

    If include_linked_assets=True the output is a .zip including linked assets alongside the .json
    """
    pages = Page.objects.descendant_of(root_page, inclusive=True).order_by('path').specific()
    if not export_unpublished:
        pages = pages.filter(live=True)

    page_data = build_page_data(pages, include_linked_assets=include_linked_assets)
    if not include_linked_assets:
        return page_data
    else:
        raise NotImplementedError('exporting with linked assets not yet supported.')


def build_page_data(pages, exported_paths=None, page_data=None, include_linked_assets=False):
    if exported_paths is None:
        exported_paths = []
    if page_data is None:
        page_data = {'pages': [], 'images': [], 'snippets': [], 'documents': []}

    for (i, page) in enumerate(pages):
        parent_path = page.path[:-(Page.steplen)]
        # skip over pages whose parents haven't already been exported
        # (which means that export_unpublished is false and the parent was unpublished)
        if (i == 0 or (parent_path in exported_paths) and page.path not in exported_paths):
            page_data['pages'].append(get_one_page_data(page))
            exported_paths.append(page.path)
            if include_linked_assets == True:

                # collect asset data; defer walking linked pages until other assets are collected
                linked_pages = []
                for obj in walk_page_foreign_key_objects(page):
                    if isinstance(obj, Image):
                        image_data = get_image_data(obj)
                        if image_data not in page_data['images']:
                            page_data['images'].append(image_data)
                    elif isinstance(obj, Document):
                        document_data = get_document_data(obj)
                        if document_data not in page_data['documents']:
                            page_data['documents'].append(document_data)
                    elif any(isinstance(obj, model) for model in SNIPPET_MODELS):
                        snippet_data = get_snippet_data(obj)
                        if snippet_data not in page_data['snippets']:
                            page_data['snippets'].append(snippet_data)
                    elif isinstance(obj, Page):
                        linked_pages.append(obj.specific)

                # recurse into all linked pages
                page_data = build_page_data(
                    linked_pages,
                    exported_paths=exported_paths,
                    page_data=page_data,
                    include_linked_assets=include_linked_assets,
                )

    return page_data


def walk_page_foreign_key_objects(page):
    """yield a (field_name, Model) tuple for each foreign key in the page data"""
    # Wagtail doesn't really expose an API for this, but it's not _too_ hard...
    page_dict = page.__dict__
    class_dict = page.__class__.__dict__
    for data_key in page_dict:
        # assume that foreign key data fields have `_id` appended to the name in the Page instance
        field_key = re.sub(r'_id$', '', data_key)
        if ('_id' in data_key and field_key in class_dict and page_dict.get(data_key) is not None
                and isinstance(class_dict[field_key].field, ForeignKey)):
            pk, Model = page_dict[data_key], class_dict[field_key].field.related_model
            obj = Model.objects.get(pk=pk)
            yield obj
        elif isinstance(page_dict[data_key], StreamValue):
            for obj in walk_stream_foreign_key_objects(stream_value.stream_block,
                                                       stream_value.stream_data):
                yield obj


def walk_stream_foreign_key_objects(stream_block, stream_data):
    """yield a (field_name, Model) tuple for each foreign key in the stream_block + stream_data"""
    child_blocks = stream_block.child_blocks
    for item in stream_data:
        block_data = item
        block = child_blocks[block_data['type']]
        if any(isinstance(block, chooser) for chooser in CHOOSER_BLOCKS):
            yield block.value_from_form(block_data['value'])
        elif isinstance(block, StructBlock) or isinstance(block, StreamBlock):
            for obj in walk_block_foreign_key_objects(block, item):
                yield obj
        elif isinstance(block, StreamBlock):
            for obj in walk_stream_foreign_key_objects(block, block_data):
                yield obj

def walk_block_foreign_key_objects(struct_block, struct_data):
    pass


def get_one_page_data(page):
    return {
        'content': json.loads(page.to_json()),
        'model': page.content_type.model,
        'app_label': page.content_type.app_label,
    }


def get_one_image_data(image):
    return {
        'classname': image.__class__.__name__,
        'module': image.__class__.__module__,
    }


def get_one_snippet_data(snippet):
    pass


def get_one_document_data(document):
    pass