from PIL import Image
import torch
from transformers import AutoModelForCausalLM, AutoProcessor, GenerationConfig

from src.vlm.prompt_template import prepare_prompt

class GenerationPipeline:

    def __init__(self, model_filepath):
        self.model_filepath = model_filepath
        self.processor = AutoProcessor.from_pretrained(
            model_filepath,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            trust_remote_code=True
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            model_filepath,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
            _attn_implementation = "sdpa"
        )

        self.generation_config = GenerationConfig.from_pretrained(
            model_filepath,
            trust_remote_code=True
        )
    
        self.generation_config.num_logits_to_keep = 20

    def prepare_inputs(self, query, images, image_modality, state):
        """As we have both image and text inputs we need to pass both inputs to the processor
        to be prepared into a suitable format.

        Args:
            query (str): The user's query.
            processor (Hugging Face processor): The processor prepares the inputs into a suitable format for the multimodal model.
            model (Hugging Face model): The model we are using. In this case we want to move the inputs to the device that the model is on.
            images (PIL image): The image which is an engineering drawing.
            image_modality (bool): Determines whether we have an optional image input.
            chat_history (list): The chatbot chat history.

        Returns:
            (dict) A dictionary of tensors. This has information such as tokenised text, pixel values, etc."""
        prompt = prepare_prompt(query, image_modality, state, retrieved_documents="")
        print("Prompt:")
        print(prompt)
        inputs = self.processor(text=prompt, images=images, return_tensors="pt").to("cuda")
        return inputs

    def generate_response(self, inputs, generation_config):
        """Generate the response.

        Args:
            model (Hugging Face model): The model we are using. In this case we want to move the inputs to the device that the model is on.
            inputs (dict): A dictionary of tensors. This has information such as tokenised text, pixel values, etc.
            generation_config (dict): A dictionary containing the configuration values for generation.
        
        Returns:
            Generation ids. These need to be unprocessed."""

        generation_ids = self.model.generate(
            **inputs,
            max_new_tokens=4096,
            generation_config=self.generation_config,
        )   
        return generation_ids

    def prepare_inputs_for_vlm_checker(self, prompt, image):
        inputs = self.processor(text=prompt, images=image, return_tensors="pt").to("auto")
        return inputs

    def run_generation_pipeline_for_vlm_checker(self, prompt, image):
        inputs = self.prepare_inputs_for_vlm_checker(prompt, image)
        generation_ids = self.generate_response(inputs, self.generation_config)
        response = self.processor.batch_decode(generation_ids, skip_special_tokens=True)[0]
        return response

    def run_generation_pipeline(self, query, image, image_modality, chat_history):
        """Run the pipeline to analyse the engineering drawing.

        Args:
            query (str): The user's query.
            image_filepath (PIL image): The image loaded with PIL.
            processor (HuggingFace processor): The Hugging Face processor.
            model (HuggingFace model): The Hugging Face model.
            generation_config (dict): A dictionary containing configuration for generation.
            image_modality (bool): Determines whether we have an optional image input.
            chat_history (list): The chatbot chat history.

        Returns:
            (str) The analysis of the engineering drawing."""
        inputs = self.prepare_inputs(query, image, image_modality, chat_history)
        generation_ids = self.generate_response(inputs, self.generation_config)
        response = self.processor.batch_decode(generation_ids, skip_special_tokens=True)[0]
        return response

    def vlm_chat(self, query, image, chat_history):
        """Handles the vision language model chat.

        Args:
            query (str): The user's query.
            image (PIL image): An optional screenshot image of any code.
            processor (HuggingFace processor): The Hugging Face processor.
            model (HuggingFace model): The Hugging Face model.
            generation_config (dict): A dictionary containing configuration for generation.
            chat_history (list): The chatbot chat history.

        Returns:
            (str) The generated response."""
        chat_history = chat_history or []
        if image is not None:
            response = self.run_generation_pipeline(query, image, True, chat_history)
            # response = "Image test"
        else:
            response = self.run_generation_pipeline(query, image, False, chat_history)
            # response = "text test"

        chat_history = chat_history + [[query, response]]

        output = f"{query}: {response}"

        with open("output.txt", "w") as file:
            file.write(output)

        return chat_history, chat_history
    
    def run_vlm(self, query, image, chat_history):
        """Handles the vision language model chat.

        Args:
            query (str): The user's query.
            image (PIL image): An optional screenshot image of any code.
            chat_history (list): The chatbot chat history.

        Returns:
            (str) The generated response."""
        chat_history = chat_history or []
        if image is not None:
            response = self.run_generation_pipeline(query, image, True, chat_history)
        else:
            response = self.run_generation_pipeline(query, image, False, chat_history)

        chat_history = chat_history + [[query, response]]

        output = f"{query}: {response}"
        return response


import re

def read_in_prompt_template(prompt_template_filepath):
    """Read in prompt template filepath.

    Args:
        prompt_template_filepath (str): Filepath to prompt template.

    Returns:
        (str) The prompt template."""
    
    with open(prompt_template_filepath, "r") as file:
        prompt_template = file.read()
    
    return prompt_template

def format_documents(retrieved_documents):
    """The retrieved documents list contains a number of dictionaries, each dictionary with a retrieval score (related to vector retrieval) and the document.
    We just need the documents and not the scores for formatting the prompt template. Hence retrieve all relevant documents and combine into one document.

    Args:
        retrieved_documents (list): The retrieved documents.

    Returns:
        (str) The documents combined."""
    
    formatted_documents = ""
    for doc in retrieved_documents:
        processed_doc = re.sub(r"id:\s*\d+\n", "", doc["document"])
        formatted_documents += f"{processed_doc}\n===============\n"
    return formatted_documents

def format_prompt_template(prompt_template, chat_history, retrieved_documents, query):
    """Format the prompt template to include chat hisotry, retrieved documents and user's query.

    Args:
        prompt_template (str): The prompt template read in from a text file stored in the config values.
        chat_history (str): Shows the chat history.
        retrieved_documents (str): The retrieved documents from the database.
        query (str): The query specified by the user.

    Returns:
        (str) A formatted prompt template with the relevant components added."""
    formatted_documents = format_documents(retrieved_documents)
    formatted_prompt_template = prompt_template.format(
        chat_history=chat_history,
        retrieved_documents=formatted_documents,
        query=query
    )
    return formatted_prompt_template

def combine_inputs_to_prompt_template(query, prompt_template_filepath, chat_history, retrieved_documents):
    """Read in prompt template then format it.

    Args:
        query (str): The query specified by the user.
        prompt_template_filepath (str): Filepath to prompt template.
        chat_history (str): Shows the chat history.
        retrieved_documents (str): The retrieved documents from the database.

    Returns:
        (str) A prepared prompt."""
    
    prompt_template = read_in_prompt_template(prompt_template_filepath)
    prompt = format_prompt_template(prompt_template, chat_history, retrieved_documents, query)
    return prompt

def prepare_prompt(query, image_modality, chat_history, retrieved_documents):
    """Apply suitable text chat format to the input prompt template.

    Args:
        query (str): The user's query.
        image_modality (bool): Determines whether we have an optional image input.
        chat_history (str): Shows the chat history.
        retrieved_documents (str): The retrieved documents from the database.

    Returns:
        (str) The prompt which will passed into the VLM in a suitable format."""

    if image_modality:
        prompt_template_filepath = "config_files/prompt_templates/with_images/main/prompt_template.txt"
        inputs = combine_inputs_to_prompt_template(query, prompt_template_filepath, chat_history, retrieved_documents)
        prompt = f"<|user|><|image_1|>{inputs}<|end|><|assistant|>"
    else:
        prompt_template_filepath = "config_files/prompt_templates/only_text/main/prompt_template.txt"
        inputs = combine_inputs_to_prompt_template(query, prompt_template_filepath, chat_history, retrieved_documents)
        prompt = f"<|user|>{inputs}<|end|><|assistant|>"
    return prompt
